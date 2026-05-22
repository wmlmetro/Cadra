# Assembly Westmetro - ITSM

This is assembly repository.
It will be automatically updated with modules listed in [odoo_packager.yml](./odoo_packager.yml) file.
Modules that are not managed by packager have to be added in separate folder `custom_addons` of this repostitory.
The modules managed by packager are packaged into [dist](./dist/) folder of this assembly.

## Assembly workflow

Typical way to update assembly repository:

1. Create new branch from stable branch. For example: 11.0-update
2. Check that _packager_ job have started on this branch.
   If it is not started, we have to start it manually from web: _CI/CD -> Run Pipeline_
3. When job is completed and repository have changes,
   then there new commit will be created on that branch (11.0-update)
4. Create merge request
5. Review changes
6. Merge to stable branch
7. Pull changes to Odoo intances that are running this assembly.

## Packager configuration format

This section describes configuration format for `odoo_packager.yml' file.

For up to date info look at [packager repository](https://gitlab.crnd.pro/crnd/docker/odoo-apps-packager/blob/d/README.md)

This configuration file use [YAML](https://yaml.org/) syntax and have following format:

```yaml
# Set this param to True if you do not need to check for missing dependencies for this repo.
no-check-deps: true

# If set to true, then no changes to addons will be made.
# Only addons specified via 'PACKAGE_ONLY_' environment variables will be updated
global-freeze: false

# List of addons that have to be added to repositorye
addons-list:
  # Usualy it is enough just to list names of addons
  - generic_condition
  - generic_rule
  - website_snippet_anchor

  # Freeze version of this addon. It will not be updated.
  # The only way to update such addons is to specify environment variable
  # PACKAGE_ONLY_website_legal_page=1
  - name: website_legal_page
    freeze: true

  # In specific cases you can specify source to get addon from.
  # Source is name of git repository, where this addon is located.
  # This feature is used in cases, when addon is available in two or more
  # repositories in different versions
  - name: crnd_web_diagram_fix
    source: crnd-web
  - name: website_logo
    source: website_logo
  - auth_saml

  # Also, you can download addons directly from Odoo Apps.
  # just specify that this addon have to be downloaded from Odoo Apps
  - name: bureaucrat_helpdesk_lite
    odoo_apps: true

# List of git repositories to fetch addons from.
git-sources:
  # Usually it is enough to specify repository url only
  - url: "https://github.com/crnd-inc/generic-addons"
  - url: "https://github.com/OCA/website"

  # also we can specify name for repository,
  # that could be used to reference this repository
  # in addons-list section.
  - url: "git@gitlab.crnd.pro:crnd/crnd-web"
    name: "crnd-web"

  # Also it is possible to specify branch to of repository to be clonned.
  # It is possible to specify one repository multiple times with different
  # branches. There is specific parametr 'no_search' which means that
  # this repository will not take part in search of source for addon.
  # It will be used as source only if it is manually
  # specified as source for addon (in addons-list)
  - url: "https://github.com/eslAmer/website"
    branch: "12.0-mig-website_logo"
    no_search: true
    name: "website_logo"

  # There are some shortcuts available.

  # This is shortcut for OCA repositories located under github.com/OCA
  # and internaly it will be converted to
  # url: "https://github.com/OCA/server-auth"
  - oca: server-auth

  # There is one more shortcut available: 'github'.
  # specification below will be automatically converted to
  # url: "https://github.com/OCA/web"
  - github: OCA/web

  # There is also shortcut for repositories
  # located on gitlab.crnd.pro available:
  - crnd: crnd/bureacurat-service

# List of known addons,
# that will not be treated as missing dependencies if not packaged.
known-addons:
  - crnd_web_diagram_plus
  - generic_condition
```

## Enable encryption of addons

Encription of addons is managed via environment variables.

To tell packager that addon `my_addon` have to be encrypted via [PyArmor](https://github.com/dashingsoft/pyarmor)
you have to specify following environment variable:

```
ARMOR_ADDON_my_addon = 1
```

As we can see, variable name consists of two parts separated by underscore (`_`):

1. `ARMOR_ADDON` which tells packager that some addon have to be encrypted
2. `my_addon` - name of addon that have to be encrypted.

Thus if you need to encrypt multiple addons, you have to specify one variable per addon.

See [GitLab documentation](https://docs.gitlab.com/ee/ci/variables/),
that describes how to configure environment variables.
Especially check [section](https://docs.gitlab.com/ee/ci/variables/#via-the-ui)
that describes how to setup environment variables from UI

## Update only specific addons

It is possible to make packager to update only specific addons.
To do this, you have to define environment variables in format:

```
PACKAGE_ONLY_addon_name=1
```

where `addon_name` is name of addon that have to be updated.

See [GitLab documentation](https://docs.gitlab.com/ee/ci/variables/),
that describes how to configure environment variables.
Especially check [section](https://docs.gitlab.com/ee/ci/variables/#via-the-ui)
that describes how to setup environment variables from UI

Also, for _Update Only_ feature, it is useful to define variables,
when [starting new pipeline manualy](https://docs.gitlab.com/ee/ci/pipelines.html#manually-executing-pipelines)

## Clone privat repositories located on third-party sources

It is possible to specify credentials for external git-sources that uses private repositories

To do this we have to add repo to sources list specifying also it's name

```yaml
git-sources:
  - url: https://github.com/my/private-repo.git
    name: my_private_repo
```

Next, you have to specify following environment variables:

```bash
PACKAGER_GIT_USER_my_private_repo=my-login PACKAGER_GIT_PASS_my_private_repo=myL_super_passoword
```
