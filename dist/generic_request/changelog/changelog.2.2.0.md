- Change default order of requests:
    - Before, requests were ordered only by `date_created DESC`
    - After, requests will be ordered by `priority DESC, date_created DESC`
    - This, fixes regression introduces in 1.30.0 version (when priorities were merged to the core)
- Improve UI, selection of related types and services on category form now moved to separate pages.
  This way, it is much easier to configure systems with large amount of services and categories.
