"""Run with python -m examples.coinbase_agent from the repository root."""

import argparse
import asyncio
import json
import os
from pathlib import Path

from agents import RunConfig, Runner, set_tracing_disabled
from dotenv import load_dotenv

from coinbase.rest import RESTClient

from .agent import build_agent
from .tools import READ_ONLY_METHODS, sdk_methods


def create_client():
    key_file = os.getenv("COINBASE_KEY_FILE")
    api_key = os.getenv("COINBASE_API_KEY") or None
    api_secret = os.getenv("COINBASE_API_SECRET") or None
    if key_file and (api_key or api_secret):
        raise ValueError(
            "Configure COINBASE_KEY_FILE or the key/secret pair, not both."
        )
    if key_file:
        return RESTClient(api_key=None, api_secret=None, key_file=key_file, timeout=30)
    if not api_key or not api_secret:
        raise ValueError(
            "Set COINBASE_KEY_FILE or both COINBASE_API_KEY and COINBASE_API_SECRET "
            "in the example's private .env file."
        )
    return RESTClient(api_key=api_key, api_secret=api_secret, timeout=30)


async def resolve_approvals(result, agent):
    while result.interruptions:
        state = result.to_state()
        for interruption in result.interruptions:
            print("\nAccount action awaiting approval:", interruption.name)
            # JSON encoding prevents terminal escape sequences in argument values.
            print(json.dumps(json.loads(interruption.arguments or "{}"), indent=2))
            try:
                answer = await asyncio.to_thread(
                    input, "Type APPROVE to execute this action, or Enter to reject: "
                )
            except EOFError:
                answer = ""
            if answer.strip() == "APPROVE":
                state.approve(interruption, always_approve=False)
            else:
                state.reject(interruption)
        result = await Runner.run(
            agent, state, max_turns=20, run_config=RunConfig(tracing_disabled=True)
        )
    return result


async def chat(client, model, read_only):
    set_tracing_disabled(True)
    agent = build_agent(client, model=model, read_only=read_only)
    print(f"Coinbase Account Agent: {len(agent.tools)} tools. Type /quit to exit.")
    print(
        "Account changes require terminal approval."
        if not read_only
        else "Read-only mode."
    )
    history = []
    while True:
        try:
            message = await asyncio.to_thread(input, "\nYou: ")
        except EOFError:
            return
        if message.strip().lower() in {"/quit", "/exit"}:
            return
        if not message.strip():
            continue
        history.append({"role": "user", "content": message})
        # Let unexpected failures stop the process rather than silently replay calls.
        result = await Runner.run(
            agent, history, max_turns=20, run_config=RunConfig(tracing_disabled=True)
        )
        result = await resolve_approvals(result, agent)
        print("\nAgent:", result.final_output)
        history = result.to_input_list()


def main():
    parser = argparse.ArgumentParser(description="Interactive Coinbase account agent")
    parser.add_argument(
        "--list-tools",
        action="store_true",
        help="List tools without keys or network calls",
    )
    parser.add_argument(
        "--read-only", action="store_true", help="Only expose reads and order previews"
    )
    parser.add_argument(
        "--check-connection",
        action="store_true",
        help="Check Coinbase API access without using OpenAI",
    )
    args = parser.parse_args()
    if args.list_tools:
        for name in sdk_methods():
            if not args.read_only or name in READ_ONLY_METHODS:
                print(
                    f"{name}: {'read/preview' if name in READ_ONLY_METHODS else 'approval required'}"
                )
        return
    load_dotenv(Path(__file__).with_name(".env"))
    try:
        client = create_client()
    except Exception:
        parser.exit(
            2,
            "Coinbase configuration is missing or invalid. See examples/coinbase_agent/README.md.\n",
        )
    try:
        if args.check_connection:
            permissions = client.get_api_key_permissions().to_dict()
            client.get_accounts(limit=1)
            print("Coinbase connection verified.")
            print(json.dumps(permissions, indent=2))
            return
        if not os.getenv("OPENAI_API_KEY"):
            parser.exit(2, "Set OPENAI_API_KEY in the example's private .env file.\n")
        asyncio.run(
            chat(client, os.getenv("OPENAI_MODEL") or "gpt-5-mini", args.read_only)
        )
    except KeyboardInterrupt:
        print(
            "\nStopped. Check account/order state before resubmitting any interrupted action."
        )
    except Exception:
        parser.exit(
            1,
            "The agent stopped after an API or runtime error. Check credentials, permissions, and connectivity. Verify account/order state before retrying an action.\n",
        )
    finally:
        client.session.close()


if __name__ == "__main__":
    main()
