import hvac
from mist.api import config


class BaseSecretController(object):
    def __init__(self, secret):
        """Initialize a secret controller given a secret

           Most times one is expected to access a controller from inside the
           secret, like this:

           secret = mist.api.secrets.models.Secret.objects.get(id=secret.id)
           secret.ctl.construct_public_from_private()
        """
        self.secret = secret


class VaultSecretController(BaseSecretController):

    client = hvac.Client
    version = me.StringField(default='kv', options=['kv', 'kv2'])

    def __init__(self, secret):
        super(VaultSecretController, self).__init__(secret)
        token = config.VAULT_TOKEN
        url = config.VAULT_ADDR

        self.client = hvac.Client(url=url, token=token)
        assert(self.client.is_authenticated())
        self.version = self.client.list_secret_backends()[self.secret.
                                                          secret_engine_name + '/']['type']

    def list_secrets(self):
        """ List all available Secrets in Secret Engine """

        if self.version == 'kv':
            list_secrets = self.client.secrets.kv.v1.list_secrets
        elif self.version == 'kv2':
            list_secrets = self.client.secrets.kv.v2.list_secrets

        api_secrets_result = list_secrets(
            mount_point=self.secret.secret_engine_name,
            # path=self.secret.name
        )

        print('The following keys found under the selected path \
            ("/v1/secret/{path}"): {keys}'.format(
            path=self.secret.secret_engine_name,
            keys=','.join(api_secrets_result['data']['keys']),
        ))

    def list_secret_engines(self):
        """ List all available Secret Engines """
        print(self.client.list_secret_backends())

    def create_secret(self, key, value):
        """ Create a Vault KV* Secret """

        if self.version == 'kv':
            create_secret = self.client.secrets.kv.v1.create_or_update_secret
        elif self.version == 'kv2':
            create_secret = self.client.secrets.kv.v2.create_or_update_secret

        create_secret(
            mount_point=self.secret.secret_engine_name,
            path=self.secret.name,
            secret={key:value},
        )
        print(self.client.secrets.kv.v1.read_secret(
              mount_point=self.secret.secret_engine_name,
              path=self.secret.name)
        )

    def read_secret(self):
        """ Read a Vault KV* Secret """

        if self.version == 'kv':
            read_secret = self.client.secrets.kv.v1.read_secret
        elif self.version == 'kv2':
            read_secret = self.client.secrets.kv.v2.read_secret

        api_response = read_secret(
            mount_point=self.secret.secret_engine_name,
            path=self.secret.name
        )
        return api_response

    def delete_secret(self):
        " Delete a Vault KV* Secret"

        if self.version == 'kv':
            delete_secret = self.client.secrets.kv.v1.delete_secret
        elif self.version == 'kv2':
            delete_secret = self.client.secrets.kv.v2.delete_secret

        delete_secret(
            mount_point=self.secret.secret_engine_name,
            path=self.secret.name
        )
