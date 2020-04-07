# Stripe Service

A service to handle stripe payment processing.

Requires the following permissions in Rehive:

permissions |
---|
admin.company.view |
admin.asset.view |
admin.transactionsubtypes.view |
admin.transactionsubtypes.add |
admin.account.view |
admin.transaction.add |
admin.transaction.change |

## Implementation

A summary of the stripe payment processor flow:

1. **CLIENT** -> POST to `/user/sessions/` with a mode of `setup`.
2. **CLIENT** -> Redirect the user to the Stripe interface with returned session id.
3. **SERVER** -> Awaits completetion of the session and updates the user details.
4. **SERVER** -> Saves the payment method on the user.
5. **CLIENT** -> POST to `/user/payments/` with an `amount` and `currency`.
6. **SERVER** -> Initiates a payment using the saved payment method.
7. **SERVER** -> Awaits completetion of the payments and updates its details.
8. **CLIENT** -> Pings the server for updates on the payment and then displays a message.

Between step 7 and 8, an additional 3D Secure step may be required from the **CLIENT**. Whether 3D Secure is required can be checked using the `next_action` object. If it contains `redirect_to_url` as the `type` then 3D Secure confirmation should be triggered by the **CLIENT**.

An example `next_action` can be seen bellow:

```
{
    type: 'redirect_to_url',
    redirect_to_url: {
      url: 'https://hooks.stripe.com/...',
      return_url: 'https://example.com'
    }
}
```

The relevant 3D Secure docs can be found here: https://stripe.com/docs/payments/3d-secure#manual-redirect