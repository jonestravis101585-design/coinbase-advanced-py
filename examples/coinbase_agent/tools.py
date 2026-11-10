"""Expose high-level RESTClient operations without exposing its HTTP internals."""

import asyncio
import inspect
import json
from typing import Any, get_type_hints

from agents import FunctionTool
from pydantic import ConfigDict, Field, ValidationError, create_model

from coinbase.rest import RESTClient

# Reviewed read/preview operations. New SDK methods require approval by default.
READ_ONLY_METHODS = frozenset("""
    get_account get_accounts get_api_key_permissions get_best_bid_ask get_candles
    get_convert_trade get_current_margin_window get_fills get_futures_balance_summary
    get_futures_position get_intraday_margin_setting get_market_trades get_order
    get_payment_method get_perps_portfolio_balances get_perps_portfolio_summary
    get_perps_position get_portfolio_breakdown get_portfolios get_product
    get_product_book get_products get_public_candles get_public_market_trades
    get_public_product get_public_product_book get_public_products
    get_transaction_summary get_unix_time list_futures_positions list_futures_sweeps
    list_orders list_payment_methods list_perps_positions preview_edit_order
    preview_limit_order_fok preview_limit_order_fok_buy preview_limit_order_fok_sell
    preview_limit_order_gtc preview_limit_order_gtc_buy preview_limit_order_gtc_sell
    preview_limit_order_gtd preview_limit_order_gtd_buy preview_limit_order_gtd_sell
    preview_limit_order_ioc preview_limit_order_ioc_buy preview_limit_order_ioc_sell
    preview_market_order preview_market_order_buy preview_market_order_sell preview_order
    preview_stop_limit_order_gtc preview_stop_limit_order_gtc_buy
    preview_stop_limit_order_gtc_sell preview_stop_limit_order_gtd
    preview_stop_limit_order_gtd_buy preview_stop_limit_order_gtd_sell
    preview_trigger_bracket_order_gtc preview_trigger_bracket_order_gtc_buy
    preview_trigger_bracket_order_gtc_sell preview_trigger_bracket_order_gtd
    preview_trigger_bracket_order_gtd_buy preview_trigger_bracket_order_gtd_sell
    """.split())


def sdk_methods():
    """Only methods defined on RESTClient itself, never inherited raw HTTP helpers."""
    return {
        name: method
        for name, method in sorted(vars(RESTClient).items())
        if not name.startswith("_") and inspect.isfunction(method)
    }


def argument_model(name, method):
    fields = {}
    hints = get_type_hints(method)
    for parameter in inspect.signature(method).parameters.values():
        if parameter.name == "self" or parameter.kind == parameter.VAR_KEYWORD:
            continue
        annotation = hints.get(parameter.name, Any)
        default = ... if parameter.default is parameter.empty else parameter.default
        if parameter.name == "client_order_id" and name not in READ_ONLY_METHODS:
            default = Field(
                ...,
                min_length=1,
                pattern=r"\S",
                description="A unique, nonempty order ID. Reuse the same ID when reconciling an uncertain submission.",
            )
        fields[parameter.name] = (annotation, default)
    # SDK **kwargs intentionally support additional endpoint parameters.
    return create_model(
        name + "Arguments",
        __config__=ConfigDict(extra="allow", strict=True),
        **fields,
    )


def make_tool(name, method, client):
    arguments_type = argument_model(name, method)
    requires_approval = name not in READ_ONLY_METHODS

    async def invoke(_context, raw_arguments):
        try:
            arguments = arguments_type.model_validate_json(raw_arguments)
        except ValidationError as error:
            # Do not echo potentially sensitive argument values into error messages.
            return json.dumps(
                {
                    "error": "invalid_arguments",
                    "details": error.errors(include_input=False, include_url=False),
                }
            )
        try:
            result = await asyncio.to_thread(
                getattr(client, name), **arguments.model_dump(exclude_unset=True)
            )
            if hasattr(result, "to_dict"):
                result = result.to_dict()
            return json.dumps(result)
        except Exception as error:
            response = getattr(error, "response", None)
            return json.dumps(
                {
                    "error": type(error).__name__,
                    "http_status": getattr(response, "status_code", None),
                    "outcome": "unknown" if requires_approval else "read_failed",
                    "message": (
                        "Do not resubmit. Check order/account state before proposing another action."
                        if requires_approval
                        else "Check credentials, API permissions, arguments, and connectivity."
                    ),
                }
            )

    description = inspect.getdoc(method) or name
    description += (
        "\nRequires human approval before execution."
        if requires_approval
        else "\nRead or preview operation; does not execute a trade."
    )
    return FunctionTool(
        name=name,
        description=description,
        params_json_schema=arguments_type.model_json_schema(),
        strict_json_schema=False,
        on_invoke_tool=invoke,
        needs_approval=requires_approval,
    )


def build_tools(client, read_only=False):
    return [
        make_tool(name, method, client)
        for name, method in sdk_methods().items()
        if not read_only or name in READ_ONLY_METHODS
    ]
