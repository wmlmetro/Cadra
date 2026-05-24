"""Verify whether generic.location.search applies our domains."""
Loc = env['generic.location'].sudo()
print("=== direct search test ===")

# 1. No filter, top 5
r = Loc.search([], limit=5, order='id')
print(f"no filter, limit=5 ids: {r.ids}")

# 2. ilike Lagos
r = Loc.search([('name', 'ilike', 'Lagos')], limit=5, order='id')
print(f"name ilike 'Lagos' ids: {r.ids}")

# 3. Our exact OR domain
domain = ['|', '|', ('name', 'ilike', 'Lagos'),
          ('street', 'ilike', 'Lagos'),
          ('city', 'ilike', 'Lagos')]
r = Loc.search(domain, limit=5, order='id')
print(f"OR(name/street/city ilike Lagos) ids: {r.ids}")

# 4. AND active
r = Loc.search(domain + [('active', '=', True)], limit=5, order='id')
print(f"... AND active=True ids: {r.ids}")

# 5. country_id=164
r = Loc.search([('country_id', '=', 164)], limit=5, order='id')
print(f"country_id=164 ids: {r.ids}")

# Are any records called something with Lagos?
r = Loc.search([('name', 'ilike', 'lagos')], limit=10)
print(f"\nany name ilike 'lagos' (lowercase): {len(r)} records")
for rec in r[:5]:
    print(f"  id={rec.id} name={rec.name!r}")
