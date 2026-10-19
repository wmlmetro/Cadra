# Run inside `odoo shell` on the TEMPLATE only, by scripts/fresh_test_tenant.sh
# (handoff 63b). Not on any tenant by hand.
#
# What `test19` carries that a database built the way CI builds one does
# not, and that the HTTP suite reaches for by name — each was a SKIP on the
# first fresh tenant (24 of its 37):
#
#   - the handoff-41 probe accounts `h41_tagger`, `h41_tagger_paired`,
#     `h41_manager` (and the deactivated `h41_leaver`) with the groups they
#     hold on `test19`, and the tagger's password the suite signs in with
#     (`tests/test_users.py`, `CADRA_H41_TAGGER_PASSWORD`);
#   - two employees, so custody and movement requests have somebody to hand
#     an asset between — created AS the suite's test credential, so they
#     carry `is_test_fixture` like everything else the suite makes;
#   - the Mailpit `ir.mail_server` row (`docs/ENVIRONMENT-FACTS.md`), so an
#     invitation is sent rather than refused 500 — when Mailpit is running.
#
# Idempotent: a second run finds each record and changes nothing.

def _seed(env):
    env.cr.execute("SELECT value FROM ir_config_parameter "
                   "WHERE key = 'cadra.database_class'")
    row = env.cr.fetchone()
    if not row or row[0] != 'test':
        raise SystemExit("refused: %r is not marked test" % env.cr.dbname)

    said = []
    Users = env['res.users'].sudo().with_context(
        active_test=False, no_reset_password=True)
    ref = env.ref
    accounts = (
        ('h41_tagger', 'H41 Tagger (fixture)', 'h41-tagger-pass', True,
         ['myservice_asset_register.group_tag_issuing_unit']),
        ('h41_tagger_paired', 'H41 Tagger Paired (fixture)', None, True,
         ['myservice_asset_register.group_asset_user',
          'myservice_asset_register.group_tag_issuing_unit']),
        ('h41_manager', 'H41 Manager (fixture)', None, True,
         ['myservice_asset_register.group_asset_manager']),
        ('h41_leaver', 'H41 Leaver (fixture)', None, False,
         ['myservice_asset_register.group_asset_user']),
    )
    for login, name, password, active, groups in accounts:
        if Users.search([('login', '=', login)]):
            said.append('%s: present' % login)
            continue
        vals = {
            'login': login, 'name': name, 'email': '%s@fixture.example' % login,
            'group_ids': [(6, 0, [ref('base.group_user').id]
                           + [ref(x).id for x in groups])],
        }
        if password:
            vals['password'] = password
        user = Users.create(vals)
        if not active:
            user.active = False
        said.append('%s: created' % login)

    Client = env['myservice.api.client'].sudo().with_context(active_test=False)
    cred = Client.search([('client_id', '=', 'test_client')], limit=1)
    if not cred or not cred.user_id:
        raise SystemExit("refused: no test_client credential user to act as")
    Employee = env['hr.employee'].with_user(cred.user_id).sudo()
    for name in ('Fixture Employee One', 'Fixture Employee Two'):
        if Employee.search([('name', '=', name)]):
            said.append('%s: present' % name)
        else:
            Employee.create({'name': name})
            said.append('%s: created' % name)

    Mail = env['ir.mail_server'].sudo()
    if not Mail.search([('smtp_host', '=', 'host.docker.internal'),
                        ('smtp_port', '=', 1025)]):
        Mail.create({'name': 'Mailpit (local dev catcher)',
                     'smtp_host': 'host.docker.internal', 'smtp_port': 1025,
                     'smtp_encryption': 'none'})
        said.append('mailpit server: created')
    else:
        said.append('mailpit server: present')

    env.cr.commit()
    for line in said:
        print('[template-fixtures] %s' % line)


_seed(env)
