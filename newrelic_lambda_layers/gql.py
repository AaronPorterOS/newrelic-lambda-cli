"""

This client is adapted from:
https://github.com/newrelic/nr-lambda-onboarding/blob/master/newrelic-cloud#L56

However this client uses a GQL client that supports schema introspection to eliminate
the error handling boilerplate for schema related errors.

Example usage:

    >>> from newrelic_lambda_layers.gql import NewRelicGQL
    >>> gql = NewRelicGQL("api key here", "account id here")
    >>> gql.get_linked_accounts()

"""

from gql import Client, gql
from gql.transport.requests import RequestsHTTPTransport


class NewRelicGQL(object):
    def __init__(self, account_id, api_key, region="us"):
        try:
            self.account_id = int(account_id)
        except ValueError:
            raise ValueError("Account ID must be an integer")

        self.api_key = api_key

        if region == "us":
            self.url = "https://api.newrelic.com/graphql"
        elif region == "eu":
            self.url = "https://api.eu.newrelic.com/graphql"
        else:
            raise ValueError("Region must be one of 'us' or 'eu'")

        transport = RequestsHTTPTransport(url=self.url, use_json=True)
        transport.headers = {"api-key": self.api_key}

        self.client = Client(transport=transport, fetch_schema_from_transport=True)

    def query(self, query, timeout=None, **variable_values):
        return self.client.execute(
            gql(query), timeout=timeout, variable_values=variable_values or None
        )

    def get_linked_accounts(self):
        """
        return a list of linked accounts for the New Relic account
        """
        res = self.query(
            """
            query ($accountId: Int!) {
              actor {
                account(id: $accountId) {
                  cloud {
                    linkedAccounts {
                      id
                      name
                      createdAt
                      updatedAt
                      authLabel
                      externalId
                    }
                  }
                }
              }
            }
            """,
            accountId=self.account_id,
        )
        return res["actor"]["account"]["cloud"]["linkedAccounts"]

    def get_license_key(self):
        """
        Fetch the license key for the NR Account
        """
        res = self.query(
            """
            query ($accountId: Int!) {
              requestContext {
                apiKey
              }
              actor {
                account(id: $accountId) {
                  licenseKey
                  id
                  name
                }
              }
            }
            """,
            accountId=self.account_id,
        )
        return res["actor"]["account"]["licenseKey"]

    def get_linked_account_by_name(self, account_name):
        """
        return a specific linked account of the New Relic account
        """
        accounts = self.get_linked_accounts()
        return next((a for a in accounts if a["name"] == account_name), None)

    def create_linked_account(self, role_arn, account_name):
        """
        create a linked account (cloud integrations account)
        in the New Relic account
        """
        res = self.query(
            """
            mutation ($accountId: Int!, $accounts: CloudLinkCloudAccountsInput!){
              cloudLinkAccount (accountId: $accountId, accounts: $accounts) {
                linkedAccounts {
                  id
                  name
                }
                errors {
                    message
                }
              }
            }
            """,
            accountId=self.account_id,
            accounts={"aws": {"arn": role_arn, "name": account_name}},
        )
        return res["cloudLinkAccount"]["linkedAccounts"][0]

    def get_integration_by_service_slug(self, linked_account_id, service_slug):
        """
        return the integration that is associated with the specified service name.
        """
        res = self.query(
            """
            query ($accountId: Int!, $linkedAccountId: Int!) {
              actor {
                account (id: $accountId) {
                  cloud {
                    linkedAccount(id: $linkedAccountId) {
                      integrations {
                        id
                        name
                        createdAt
                        updatedAt
                        service {
                          slug
                          isEnabled
                        }
                      }
                    }
                  }
                }
              }
            }
            """,
            accountId=self.account_id,
            linkedAccountId=linked_account_id,
        )
        integrations = res["actor"]["account"]["cloud"]["linkedAccount"]["integrations"]
        return next(
            (i for i in integrations if i["service"]["slug"] == service_slug), None
        )

    def is_integration_enabled(self, linked_account_id, service_slug):
        integration = self.get_integration_by_service_slug(
            linked_account_id, service_slug
        )
        return integration and integration["service"]["isEnabled"]

    def enable_integration(self, linked_account_id, provider_slug, service_slug):
        """
        enable monitoring of a Cloud provider service (integration)
        """
        res = self.query(
            """
            mutation ($accountId:Int!, $integrations: CloudIntegrationsInput!) {
              cloudConfigureIntegration (
                accountId: $accountId,
                integrations: $integrations
              ) {
                integrations {
                  id
                  name
                  service {
                    id
                    name
                  }
                }
                errors {
                  linkedAccountId
                  message
                }
              }
            }
            """,
            accountId=self.account_id,
            integrations={
                provider_slug: {service_slug: [{"linkedAccountId": linked_account_id}]}
            },
        )
        return res["cloudConfigureIntegration"]["integrations"][0]
