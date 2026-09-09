# Reading an auth failure

`POST /api/v1/auth/token` answers exactly one thing when the credential does
not work:

```json
{"error": {"code": "unauthorized",
           "message": "Invalid client credentials",
           "request_id": "9f2c…",
           "details": {"http_status": 401}}}
```

**That is deliberate and it is not going to change.** Four different things
produce it, and telling an unauthenticated caller which one would let anyone
enumerate our client ids by watching the answers differ. The person debugging
at 11pm and the person probing the endpoint are the same shape of request; the
server cannot tell them apart, so it tells neither.

What it does instead is write the cause to the server log, against the
`request_id` that response carries. **Quote the `request_id`** and the answer
is one grep away.

## The log line

Logger `cadra.auth`, one line per attempt:

```
… WARNING <db> cadra.auth: request_id=9f2c… client_id=Vendra outcome=case_mismatch matched=vendra
… WARNING <db> cadra.auth: request_id=…    client_id=vendra outcome=bad_secret
… WARNING <db> cadra.auth: request_id=…    client_id=vendra outcome=inactive
… WARNING <db> cadra.auth: request_id=…    client_id=vendr  outcome=no_such_client
… INFO    <db> cadra.auth: request_id=…    client_id=vendra outcome=ok
```

```bash
# staging / prod
kubectl logs deploy/odoo-19 -n cadra-dev --since=1h | grep cadra.auth | grep <request_id>

# local
docker compose -f docker-compose.yml -f docker-compose.19.yml logs odoo | grep cadra.auth
```

## What each outcome means

| outcome | what happened | what to do |
|---|---|---|
| `bad_secret` | The client id is right; the secret is not. | Rotate the secret (API Clients form → **Rotate Secret**) and update the caller. The stored value is a hash — the old secret cannot be recovered. |
| `case_mismatch` | The id differs only in case from a real client. `=` on a Postgres varchar is case-sensitive, so `Vendra` and `vendra` are different clients. `matched=` names the real one. | Fix the caller's config to the id in `matched=`. This is the one that cost an hour on staging. |
| `inactive` | The client exists and is archived. | Un-archive it, or point the caller at a live client. Note the secret may still be correct — reactivating is usually all that is needed. |
| `no_such_client` | No client with that id, in any case, archived or not. | The tenant is probably wrong. Client records are **per database**: a credential minted on `nrs19` does not exist on `jaizbankplc`, and the host in the URL is what selects the database. |
| `ok` | A token was minted. | Nothing. It is logged so "did this credential ever work?" — the second question anybody asks — has an answer. |

## What is never logged

The client **secret**. Not hashed, not truncated, not as a length. If you find
one in a log, that is a defect, not a debugging aid.

The client **id** is logged as sent, because it is half of a credential pair
and it arrived in the clear — that is the whole point of the `case_mismatch`
line. It is sanitised first (printable ASCII, truncated), because it is
unauthenticated caller-supplied text and a newline in it would otherwise let
the caller forge log lines under our own logger name.

**One caveat worth knowing:** a caller who swaps the two fields will have put
its secret in `client_id`, and that value is logged. If that happens, rotate.

## Other 401s

`request_id` is on every error envelope, but only `/auth/token` writes a
matching `cadra.auth` line today. A 401 from any other route is the bearer
token being absent, malformed or expired — `/auth/refresh` answers one generic
401 for every cause as well, for the same reason.
