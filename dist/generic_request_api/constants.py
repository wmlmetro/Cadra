import passlib.context

API_PREFIX = '/api/requests'
API_PREFIX_INTERNAL = '%s/internal' % API_PREFIX
API_PREFIX_PUBLIC = '%s/public' % API_PREFIX
API_PREFIX_REST = '%s/rest' % API_PREFIX

# Crypt params
API_KEY_SIZE = 20  # in bytes
INDEX_SIZE = 8  # in hex digits, so 4 bytes, or 20% of the key
KEY_CRYPT_CONTEXT = passlib.context.CryptContext(
    # default is 29000 rounds which is 25~50ms, which is probably unnecessary
    # given in this case all the keys are completely random data: dictionary
    # attacks on API keys isn't much of a concern
    ['pbkdf2_sha512'], pbkdf2_sha512__rounds=6000,
)
