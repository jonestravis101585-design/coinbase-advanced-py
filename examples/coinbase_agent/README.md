# Coinbase Account Agent

An interactive terminal agent for your Coinbase Advanced Trade account, using the
OpenAI Agents SDK. It exposes all **105 high-level RESTClient methods** in this
fork: 63 reads/previews and 42 operations requiring per-call human approval.

Tools cover accounts and balances, market data, fees, payment-method lookup,
order previews, placing/editing/cancelling orders, conversions, portfolios and
the futures/perpetuals methods available through `RESTClient`. An available tool
does not imply your Coinbase account or API key has permission to use it.

This is a runnable agent example. It does not deploy a hosted service or change
the existing coinbase2LGit ChatGPT plugin. WebSocket subscriptions, the separate
`coinbase.deribit` Global Derivatives clients, arbitrary HTTP requests, cash
withdrawals, and blockchain-wallet actions are outside this example's scope.

## Install

Use Python 3.10 or newer. From the root of your fork:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r examples/coinbase_agent/requirements.txt
cp examples/coinbase_agent/.env.example examples/coinbase_agent/.env
```

On Windows PowerShell, activate with `.venv\Scripts\Activate.ps1` and use
`Copy-Item` instead of `cp` if needed.

## Connect your account

1. Obtain a Coinbase CDP API key for your Coinbase Advanced Trade account using
   [Coinbase's authentication documentation](https://docs.cdp.coinbase.com/get-started/authentication/overview).
2. Keep the downloaded key JSON outside the repository. In the private
   `examples/coinbase_agent/.env`, set `COINBASE_KEY_FILE` to its absolute path.
   Alternatively, leave that setting empty and fill in `COINBASE_API_KEY` and
   `COINBASE_API_SECRET`. Do not configure both methods.
3. Set `OPENAI_API_KEY` for the agent's model. API usage is billed separately
   from a ChatGPT subscription. `OPENAI_MODEL` can select another model you can access.
4. Check Coinbase access (uses Coinbase only; does not call OpenAI):

   ```bash
   python -m examples.coinbase_agent --check-connection
   ```

The connection check reads API permissions and one page of accounts; it does not
submit orders. A connected ChatGPT plugin does not supply credentials to this
standalone process. Never put API secrets in chat, commits, issues, or pull requests.
The repository is public. Keep `.env` private and store your key JSON outside it.

## Use the agent

```bash
# Full RESTClient tool set; each account change pauses for approval.
python -m examples.coinbase_agent

# Reads and previews only; changing tools are omitted entirely.
python -m examples.coinbase_agent --read-only

# Inspect the tool inventory locally without credentials or network requests.
python -m examples.coinbase_agent --list-tools
```

Try: "Show my balances", "List my open orders", or "Preview buying 10 USD of
BTC-USD without placing the order." Use `/quit` to exit.

For each changing operation, the terminal displays the tool name and exact
arguments. Type `APPROVE` to execute that one call; Enter or EOF rejects it.
There is no blanket approval. Even creating a conversion quote is gated
conservatively. `--read-only` plus a view-only Coinbase key is an option for
initial account inspection. Trades require the appropriate Coinbase permissions.

Order submissions require a nonempty `client_order_id`. The agent does not
automatically retry Coinbase calls. After a timeout, process interruption, or
uncertain response, reconcile order/account state before any new submission.
An accepted order is not necessarily filled. Approval checks the proposed call;
it cannot guarantee a price or prevent market losses.

Conversation history is held in memory and sent to OpenAI as model context,
including account tool results needed for the conversation. The example disables
Agents tracing and requests `store=False`; these settings do not override API
provider retention policies. It writes no conversation or approval state to disk.

## Development

Tool schemas come from SDK signatures and type hints, including optional
parameters and endpoint `**kwargs`. Inherited transport methods such as `get`,
`post`, `send_request`, credential access, and constructors are never tools.
Only an explicitly reviewed set of reads/previews bypasses approval. New SDK
methods require approval unless added to that reviewed set.

The agent dependency is optional and isolated from the SDK's normal requirements.
Agents SDK 0.13.6 is pinned because later releases require a WebSocket dependency
incompatible with this fork's `websockets<14` requirement.
The OpenAI client is pinned to 2.26.0 to match that Agents SDK release.

Run the offline tests (no keys, network calls, trades, or model charges):

```bash
python -m unittest discover -s examples/coinbase_agent/tests -v
```

Tests use the real Agents runner with a scripted model and mocked Coinbase
transport to verify reads, approvals, rejection, schemas, and uncertain writes.
