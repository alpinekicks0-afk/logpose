# Switching accounts on

The accounts code ships switched off. Until the pieces below exist, the Account
page says "Accounts are not switched on yet" and the rest of the site is
unaffected. Each piece is needed twice: once for preview builds, once for the
live site, so that testing never touches real members' data.

Nothing in this file is secret. Secrets are entered in Cloudflare by the site
owner and never committed.

## 1. Database (Cloudflare D1)

Cloudflare dashboard → Storage & Databases → D1 → Create database.

- `logpose-accounts` for the live site
- `logpose-accounts-preview` for previews

Each has a Database ID. Those two IDs go into `wrangler.jsonc`:

```jsonc
"d1_databases": [
  { "binding": "DB", "database_name": "logpose-accounts", "database_id": "<live id>" }
],
"vars": { "TURNSTILE_SITE_KEY": "<site key>", "ADMIN_USERNAMES": "<your username>" },
"previews": {
  "d1_databases": [
    { "binding": "DB", "database_name": "logpose-accounts-preview", "database_id": "<preview id>" }
  ],
  "vars": { "TURNSTILE_SITE_KEY": "<site key>", "ADMIN_USERNAMES": "<your username>" }
}
```

The tables are created automatically on the first request; there is no
migration step.

## 2. Captcha (Cloudflare Turnstile)

Cloudflare dashboard → Turnstile → Add widget. Mode: Managed. Hostnames:
`logpose.cards` and `alpinekicks0.workers.dev` (covers preview addresses).

- Site key: public, goes in `wrangler.jsonc` as `TURNSTILE_SITE_KEY`.
- Secret key: goes in Cloudflare as the secret `TURNSTILE_SECRET`.

## 3. Sign in with Google

Google Cloud console → APIs & Services → Credentials → Create credentials →
OAuth client ID → Web application. Authorised redirect URIs:

- `https://logpose.cards/api/auth/google/callback`
- `https://<preview host>/api/auth/google/callback`

On the consent screen: user type External, app name Log Pose, and publish it
(the only scope used is `openid`, which needs no Google review).

Secrets: `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`.

## 4. Sign in with Discord

discord.com/developers/applications → New Application → OAuth2 → Redirects:

- `https://logpose.cards/api/auth/discord/callback`
- `https://<preview host>/api/auth/discord/callback`

Secrets: `DISCORD_CLIENT_ID`, `DISCORD_CLIENT_SECRET`.

Either provider can be left out; the sign-in page only shows the ones that
have both values set.

## 5. Entering the secrets

Live site: Cloudflare dashboard → Workers & Pages → logpose → Settings →
Variables and Secrets → Add → type Secret.

Previews do not inherit the live site's secrets. Set them for all previews
with `npx wrangler preview base-config secret put <NAME>` (or in the
dashboard's preview settings for the Worker).

The five secrets: `TURNSTILE_SECRET`, `GOOGLE_CLIENT_ID`,
`GOOGLE_CLIENT_SECRET`, `DISCORD_CLIENT_ID`, `DISCORD_CLIENT_SECRET`.

## 6. Reading reports

Members can report an account or a chat. Reports appear in a Reports tab in
the Account section for the usernames listed in `ADMIN_USERNAMES`
(comma-separated). Create your own account first, then list its username.

## Testing locally

```
node tools/test_accounts.mjs      # API checks against an in-memory database
node tools/dev_server.mjs 8787    # the whole site with stand-in sign-in and captcha
```
