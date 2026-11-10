# Set up the agent on your Windows PC

## 1. Install Python

Install Python 3.12 or newer from [python.org](https://www.python.org/downloads/windows/).
Include the Python launcher when the installer offers it. Then close and reopen
any terminal windows. You do not need Git or an administrator terminal for the
agent launcher.

## 2. Download the agent

Open the [agent branch](https://github.com/jonestravis101585-design/coinbase-advanced-py/tree/codex/coinbase-account-agent),
select **Code > Download ZIP**, then right-click the download and choose
**Extract All**. Open the extracted folder. The launcher must run from the
extracted folder, not from inside the ZIP viewer.

Double-click **Start Coinbase Agent.cmd**. Its first run installs dependencies
into the folder's `.venv` environment. This needs internet access and may take a
few minutes. Future launches reuse that environment. The launcher does not
change PowerShell execution policy, open a network port, or start a background
service.

If Windows displays a security prompt, inspect the script and verify that you
downloaded it from your own fork. Do not disable Windows security protections.

## 3. Prepare your API keys

Create a Coinbase **Secret API Key** for your Coinbase account using
[Coinbase's instructions](https://docs.cdp.coinbase.com/coinbase-app/authentication-authorization/api-key-authentication).
Select **ECDSA (ES256)**. Enable **View**; enable **Trade** if you want trading.
Transfer permission is needed only for supported transfer operations.

Click **Download API key** in Coinbase's key dialog. Move the JSON file to a
private folder outside the extracted repository, for example
`C:\Users\YourName\Documents\coinbase-keys`. The agent references the file where
you store it, so keep it at that location.

Create an OpenAI API key at [OpenAI's API key page](https://platform.openai.com/api-keys).
The account needs API billing or available credits. ChatGPT and API billing are
separate. Do not share either provider's credentials in chat or upload them to
GitHub.

## 4. Run local setup

In the launcher menu, choose **1. Set up API keys on this computer**.

- Select the downloaded Coinbase key JSON in the file picker. If the picker is
  unavailable, enter its full path in the terminal.
- Paste your OpenAI API key when prompted. Input is hidden, so you may see no
  characters while pasting. Press Enter to continue.
- Press Enter to accept `gpt-5-mini`, or enter another model you can access.

The wizard checks the Coinbase key format locally and saves settings to the
Git-ignored `examples/coinbase_agent/.env`. It makes no API requests and submits
no trades. It does not copy or alter your Coinbase JSON file. Existing settings
are replaced only if you type `REPLACE` in the wizard.

Credentials are stored as local files, not in an encrypted credential vault.
Protect your Windows account and disk, and keep this folder out of shared or
publicly synced locations. Do not upload the folder with credentials attached.

## 5. Verify the connection

Choose **2. Check Coinbase connection**. Success prints:

```text
Coinbase connection verified.
```

This reads API permissions and accounts. It submits no orders and does not use
OpenAI. If it fails, check the downloaded key, View permission, selected
portfolio, and any IP allowlist against this PC's outbound public IP.

## 6. Start using the agent

Choose **3. Start read-only chat**, then ask **Show my balances**. Model requests
use your OpenAI account. Account information needed for the conversation is
sent to the model provider.

Enter `/quit` to return to the menu. Choose **4. Start full agent** when you want
the account-changing tools available. The agent shows each proposed action's
exact arguments and waits for you to type `APPROVE` in the terminal. Press Enter
to reject. Approval does not guarantee execution price or prevent trading losses.

Choose **0. Exit** to leave the menu. Closing the agent stops future local
actions; orders already submitted can remain active on Coinbase. Keep your PC
awake and connected while you use it. This setup provides no iPhone interface
or remote access configuration.

## Troubleshooting

- **Python not found:** install Python with its launcher, then reopen the agent.
- **Installation error:** check internet access and read the error in the
  launcher window. Rerun the launcher after resolving it.
- **No menu after downloading:** use Extract All first; do not run inside a ZIP.
- **Key file rejected:** select Coinbase's downloaded API key JSON, keep it
  outside the repository, and check that it uses an accepted private key format.
- **Existing environment variables:** the agent preserves your process's
  `OPENAI_*` and `COINBASE_*` variables. If these conflict with local settings,
  remove or correct them in the launching environment and reopen the agent.
- **Updating:** download and extract a new copy, then run setup there. Do not
  paste old credentials into GitHub or copy the `.venv` folder between PCs.

For manual commands and the full scope, see [the agent README](README.md).
