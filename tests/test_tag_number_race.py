"""Twenty receipts at once get twenty numbers (handoff 63b §3b).

Vendra report 58: two chairs of one receipt, sent by two INT-03 calls 100 ms
apart, both came back `NRS-FURN-018` (`test19`, assets 106911 and 106912).
The location-prefix generator read the highest number under the prefix and
added one; two requests in flight read the same highest, because each reads
through its own snapshot. Where report 63's unique index stands the second
create was a `409`, so a receipt lost a unit to a race; where it does not
(`test19`, 68 such numbers) both were minted.

The number now comes from a Postgres sequence per prefix
(`nrs.asset._tag_sequence`), which never hands one value to two
transactions. This fires twenty creates at one prefix at once and requires
twenty 201s and twenty different numbers. With the receipt gates ON a
receipt gets no label at the door — the label is minted at the tagging
request, numbered with the asset code — so the same race is asked of the
asset code, the number those labels will carry.

It needs a server with more than one worker to race at all; the committed
`odoo.19.conf` has two, and CI runs that file.
"""
import uuid
from concurrent.futures import ThreadPoolExecutor

import requests

from . import gates

N = 20


def test_twenty_concurrent_receipts_at_one_prefix_get_twenty_numbers(client):
    run = uuid.uuid4().hex[:8]
    # One category and no location: one prefix for all twenty
    # (`_tag_prefix` — the brand's short code, then the class's code).
    bodies = [gates.receipt_body(client, name=f"pytest-race63b-{run}-{i:02d}",
                                 category_id=1)
              for i in range(N)]
    gated = gates.receipt_gated(client)
    headers = dict(client.session.headers)

    def post(body):
        # Not `client`: a `requests.Session` is not shared across threads.
        return requests.post(f"{client.base}/api/v1/assets", json=body,
                             headers=headers, timeout=120)

    with ThreadPoolExecutor(max_workers=N) as pool:
        responses = list(pool.map(post, bodies))

    refused = [(r.status_code, r.text[:300]) for r in responses
               if r.status_code != 201]
    assert not refused, (
        "%d of %d concurrent receipts at one prefix were refused — the "
        "first: %s" % (len(refused), N, refused[0]))

    rows = [r.json()["data"] for r in responses]
    key = "asset_code" if gated else "tag"
    numbers = [row[key] for row in rows]
    assert all(numbers), f"a receipt came back with no `{key}`: {numbers}"
    assert len(set(numbers)) == N, (
        "%d receipts at once got %d distinct `%s` values; repeated: %s" % (
            N, len(set(numbers)), key,
            sorted({n for n in numbers if numbers.count(n) > 1})))
    if not gated:
        prefixes = {n.rsplit("-", 1)[0] for n in numbers}
        assert len(prefixes) == 1, (
            f"the twenty were meant to share one prefix and used {prefixes}")
