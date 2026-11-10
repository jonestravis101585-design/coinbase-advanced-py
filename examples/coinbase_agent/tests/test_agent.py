import io
import json
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from agents import Model, ModelResponse, RunConfig, Runner, Usage
from jsonschema import Draft202012Validator
from openai.types import responses
from requests.exceptions import Timeout
from requests_mock import Mocker

from coinbase.rest import RESTClient
from examples.coinbase_agent import tools as account_tools
from examples.coinbase_agent.__main__ import create_client, resolve_approvals
from examples.coinbase_agent.agent import build_agent
from tests.constants import TEST_API_KEY, TEST_API_SECRET


class ScriptedModel(Model):
    """Exercise the real runner without a model service or API key."""

    def __init__(self, method, arguments):
        self.method = method
        self.arguments = arguments
        self.calls = 0

    async def get_response(self, *args, **kwargs):
        self.calls += 1
        if self.calls == 1:
            output = [
                responses.ResponseFunctionToolCall(
                    id="tool-item",
                    call_id="call-1",
                    name=self.method,
                    arguments=json.dumps(self.arguments),
                    type="function_call",
                )
            ]
        else:
            output = [
                responses.ResponseOutputMessage(
                    id="message-1",
                    role="assistant",
                    type="message",
                    status="completed",
                    content=[
                        responses.ResponseOutputText(
                            type="output_text", text="Done", annotations=[]
                        )
                    ],
                )
            ]
        return ModelResponse(output=output, usage=Usage(), response_id=None)

    async def stream_response(self, *args, **kwargs):
        raise NotImplementedError("Streaming is not used in these tests")
        yield  # pragma: no cover


class ToolInventoryTests(unittest.TestCase):
    def setUp(self):
        self.client = RESTClient(api_key=None, api_secret=None)
        self.addCleanup(self.client.session.close)

    def test_complete_inventory_and_transport_exclusion(self):
        tools = {tool.name: tool for tool in account_tools.build_tools(self.client)}
        self.assertEqual(len(tools), 105)
        self.assertEqual(set(tools), set(account_tools.sdk_methods()))
        self.assertEqual(len(account_tools.READ_ONLY_METHODS), 63)
        self.assertTrue(account_tools.READ_ONLY_METHODS <= tools.keys())
        for name in (
            "get",
            "post",
            "put",
            "delete",
            "send_request",
            "set_headers",
            "__init__",
        ):
            self.assertNotIn(name, tools)
        for name, tool in tools.items():
            self.assertEqual(
                tool.needs_approval, name not in account_tools.READ_ONLY_METHODS
            )
            Draft202012Validator.check_schema(tool.params_json_schema)
        for name in account_tools.READ_ONLY_METHODS:
            self.assertTrue(name.startswith(("get_", "list_", "preview_")))

    def test_read_only_mode_omits_account_changes(self):
        tools = account_tools.build_tools(self.client, read_only=True)
        self.assertEqual({tool.name for tool in tools}, account_tools.READ_ONLY_METHODS)
        self.assertTrue(all(tool.needs_approval is False for tool in tools))

    def test_signatures_preserve_decimal_strings_and_required_fields(self):
        tools = {tool.name: tool for tool in account_tools.build_tools(self.client)}
        buy_schema = tools["market_order_buy"].params_json_schema
        self.assertEqual(set(buy_schema["required"]), {"client_order_id", "product_id"})
        self.assertIn(
            {"type": "string"}, buy_schema["properties"]["quote_size"]["anyOf"]
        )
        self.assertTrue(buy_schema["additionalProperties"])
        self.assertIn(
            "order_configuration", tools["create_order"].params_json_schema["required"]
        )


class AgentApprovalTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.client = RESTClient(TEST_API_KEY, TEST_API_SECRET)
        self.addCleanup(self.client.session.close)
        self.order = {
            "client_order_id": "unique-order-1",
            "product_id": "BTC-USD",
            "quote_size": "10.00",
        }

    async def run_call(self, name, arguments):
        agent = build_agent(self.client, model=ScriptedModel(name, arguments))
        result = await Runner.run(
            agent,
            "Exercise the requested tool",
            run_config=RunConfig(tracing_disabled=True),
        )
        return agent, result

    async def test_read_executes_and_serializes_account_data(self):
        with Mocker() as mock:
            mock.get(
                "https://api.coinbase.com/api/v3/brokerage/accounts",
                json={"accounts": [{"uuid": "test-account"}], "has_next": False},
            )
            _, result = await self.run_call(
                "get_accounts", {"limit": 1, "cursor": "next-page"}
            )
            self.assertFalse(result.interruptions)
            self.assertEqual(mock.call_count, 1)
            self.assertIn("limit=1", mock.last_request.query)
            outputs = [
                item.output
                for item in result.new_items
                if item.type == "tool_call_output_item"
            ]
            self.assertEqual(
                json.loads(outputs[0])["accounts"][0]["uuid"], "test-account"
            )

    async def test_order_cannot_execute_until_exact_terminal_approval(self):
        with Mocker() as mock:
            mock.post(
                "https://api.coinbase.com/api/v3/brokerage/orders",
                json={"success": True},
            )
            agent, result = await self.run_call("market_order_buy", self.order)
            self.assertEqual(len(result.interruptions), 1)
            self.assertEqual(mock.call_count, 0)
            with patch("builtins.input", return_value="APPROVE"), redirect_stdout(
                io.StringIO()
            ):
                result = await resolve_approvals(result, agent)
            self.assertFalse(result.interruptions)
            self.assertEqual(mock.call_count, 1)
            payload = mock.last_request.json()
            self.assertEqual(payload["client_order_id"], "unique-order-1")
            self.assertEqual(
                payload["order_configuration"]["market_market_ioc"]["quote_size"],
                "10.00",
            )

    async def test_rejection_and_eof_never_submit(self):
        for response in ("", "yes", "approve", EOFError()):
            with self.subTest(response=type(response).__name__), Mocker() as mock:
                agent, result = await self.run_call("market_order_buy", self.order)
                options = (
                    {"side_effect": response}
                    if isinstance(response, Exception)
                    else {"return_value": response}
                )
                with patch("builtins.input", **options), redirect_stdout(io.StringIO()):
                    await resolve_approvals(result, agent)
                self.assertEqual(mock.call_count, 0)

    async def test_transfer_and_conversion_are_also_gated(self):
        cases = {
            "move_portfolio_funds": {
                "value": "1",
                "currency": "USD",
                "source_portfolio_uuid": "one",
                "target_portfolio_uuid": "two",
            },
            "commit_convert_trade": {
                "trade_id": "one",
                "from_account": "two",
                "to_account": "three",
            },
            "cancel_orders": {"order_ids": ["one"]},
        }
        with Mocker() as mock:
            for name, arguments in cases.items():
                _, result = await self.run_call(name, arguments)
                self.assertEqual(len(result.interruptions), 1)
            self.assertEqual(mock.call_count, 0)

    async def test_validation_stops_empty_ids_and_wrong_types(self):
        tools = {tool.name: tool for tool in account_tools.build_tools(self.client)}
        with Mocker() as mock:
            for bad in ("", "   ", None, 123):
                output = await tools["market_order_buy"].on_invoke_tool(
                    None, json.dumps({**self.order, "client_order_id": bad})
                )
                self.assertEqual(json.loads(output)["error"], "invalid_arguments")
            output = await tools["get_accounts"].on_invoke_tool(
                None, '{"limit": "wrong"}'
            )
            self.assertEqual(json.loads(output)["error"], "invalid_arguments")
            self.assertEqual(mock.call_count, 0)

    async def test_timeout_does_not_retry_or_echo_exception_secrets(self):
        tool = next(
            tool
            for tool in account_tools.build_tools(self.client)
            if tool.name == "market_order_buy"
        )
        with patch.object(
            self.client, "market_order_buy", side_effect=Timeout("sensitive-secret")
        ) as method:
            output = await tool.on_invoke_tool(None, json.dumps(self.order))
            self.assertEqual(method.call_count, 1)
            self.assertEqual(json.loads(output)["outcome"], "unknown")
            self.assertNotIn("sensitive-secret", output)

    async def test_preview_does_not_submit_an_order(self):
        with Mocker() as mock:
            mock.post(
                "https://api.coinbase.com/api/v3/brokerage/orders/preview",
                json={"errs": []},
            )
            _, result = await self.run_call(
                "preview_market_order_buy",
                {"product_id": "BTC-USD", "quote_size": "10"},
            )
            self.assertFalse(result.interruptions)
            self.assertEqual(mock.call_count, 1)
            self.assertTrue(mock.last_request.url.endswith("/orders/preview"))


class ConfigurationTests(unittest.TestCase):
    def test_missing_and_conflicting_credentials_fail_without_network(self):
        for environment in (
            {},
            {"COINBASE_API_KEY": "key"},
            {"COINBASE_KEY_FILE": "file", "COINBASE_API_KEY": "key"},
        ):
            with self.subTest(keys=list(environment)), patch.dict(
                "os.environ", environment, clear=True
            ):
                with self.assertRaises(ValueError):
                    create_client()

    def test_key_file_explicitly_avoids_import_time_environment_defaults(self):
        with patch.dict(
            "os.environ", {"COINBASE_KEY_FILE": "/private/key.json"}, clear=True
        ):
            with patch("examples.coinbase_agent.__main__.RESTClient") as constructor:
                create_client()
                constructor.assert_called_once_with(
                    api_key=None,
                    api_secret=None,
                    key_file="/private/key.json",
                    timeout=30,
                )


if __name__ == "__main__":
    unittest.main()
