# Authentication

Grove has two credentials.

A person uses the OAuth2 password grant. `POST /api/v1/auth/token` takes form fields `username` (the email) and `password`. The response is a bearer access token and a refresh token. Swagger's Authorize button calls this route.

A machine uses `X-API-Key`. Keys are created by an admin and shown once. A key can read the catalog, stock, orders, growers, and the summary. It cannot sell, price, upload, or change a person, even when the owner is an admin. That split is deliberate: a key on a board in the shop should not be able to empty the house.

## Scopes

The role decides the ceiling. The access token carries a subset of that ceiling. On each request the effective scopes are the intersection, so demoting someone takes effect before the access token expires.

| Scope | Clerk | Manager | Admin | API key |
| --- | --- | --- | --- | --- |
| `catalog:read` | yes | yes | yes | yes |
| `catalog:write` | | yes | yes | |
| `inventory:read` | yes | yes | yes | yes |
| `inventory:write` | | yes | yes | |
| `orders:read` | yes | yes | yes | yes |
| `orders:write` | yes | yes | yes | |
| `orders:fulfill` | | yes | yes | |
| `suppliers:read` | yes | yes | yes | yes |
| `suppliers:write` | | yes | yes | |
| `reports:read` | yes | yes | yes | yes |
| `audit:read` | | yes | yes | |
| `admin` | | | yes | |

Catalog `GET` is public, so the board outside the login can render. Everything that changes a row requires a scope.

If the client asks for scopes at the token endpoint, Grove grants the intersection with the role. An empty request grants the whole role. A request that intersects to nothing is rejected.

## Refresh

Refresh tokens are stored as a SHA-256 hash. `POST /api/v1/auth/refresh` checks the hash, revokes that row, and issues a new pair. Presenting the old refresh token again fails. Logout revokes the refresh token that is sent. Changing a password revokes every refresh token for the account. The current access token keeps working until it expires; that window is `ACCESS_TOKEN_MINUTES`.

## Websockets

Browser websockets cannot set `Authorization`. The floor passes the access token once, as `token` on `/api/v1/live/ws`. Access logs may record that URL. Keep the access token short, which it already is. Do not put a refresh token on the URL.

## Production

`APP_ENV=production` refuses to start when `SECRET_KEY` is the development placeholder or shorter than 32 characters. Tokens are HMAC-SHA256. Passwords are bcrypt.
