# Handoff 63b §3b — where a category policy save spends its time.
# Run in `odoo shell -d test19f` (a throwaway restored from the template).
# Builds a class of N assets, then profiles exactly what
# PATCH /asset-categories/<id> runs for a policy field, as the
# controller does (sudo search, _sync_policy_from_category,
# _apply_depreciation, flush). Rolls everything back.
import cProfile, io, os, pstats, time

N = int(os.environ.get('N', '3000'))
Asset = env['nrs.asset'].sudo()
if env.cr.dbname == 'test19':
    # The real class: category 1, ~19k assets. Nothing built, all rolled back.
    cat = env['nrs.asset.category'].sudo().browse(1)
else:
    assert env.cr.dbname == 'test19f', env.cr.dbname
    cat = env['nrs.asset.category'].sudo().create({
        'name': 'Profile 63b', 'code': 'PRF63B',
        'depreciation_method': 'straight_line', 'useful_life_months': 60})
    t = time.time()
    Asset.with_context(tracking_disable=True, mail_create_nolog=True).create([{
        'name': 'Profile asset %d' % i, 'category_id': cat.id,
        'acquisition_cost': 100000.0 + i, 'acquisition_date': '2024-01-15',
    } for i in range(N)])
    env.flush_all()
    print('built %d assets in %.1f s' % (N, time.time() - t))
MONTHS = (cat.useful_life_months or 60) + 12
print('category %d %r, useful_life_months -> %d' % (cat.id, cat.name, MONTHS))


def save(months):
    phases = {}
    t0 = time.time()
    cat.write({'useful_life_months': months})
    phases['cat.write'] = time.time() - t0
    t1 = time.time()
    assets = Asset.search([('category_id', '=', cat.id),
                           ('use_category_policy', '=', True)])
    phases['search'] = time.time() - t1
    t2 = time.time()
    assets._sync_policy_from_category()
    env.flush_all()
    phases['_sync_policy_from_category+flush'] = time.time() - t2
    t3 = time.time()
    if os.environ.get('SECOND_APPLY', '1') == '1':
        # The route until handoff 63b called it again after the sync.
        assets._apply_depreciation()
    env.flush_all()
    phases['_apply_depreciation+flush'] = time.time() - t3
    phases['TOTAL'] = time.time() - t0
    return len(assets), phases


q0 = env.cr.sql_log_count
pr = cProfile.Profile()
pr.enable()
n, phases = save(MONTHS)
pr.disable()
print('assets %d | queries %d' % (n, env.cr.sql_log_count - q0))
for k, v in phases.items():
    print('  %-36s %6.2f s   %6.2f ms/asset' % (k, v, 1000 * v / max(n, 1)))
s = io.StringIO()
pstats.Stats(pr, stream=s).sort_stats('cumulative').print_stats(35)
print(s.getvalue()[:9000])
env.cr.rollback()
print('rolled back')
