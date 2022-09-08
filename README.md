<p align="center">
  <img width="64" src="https://avatars2.githubusercontent.com/u/22204821?s=200&v=4" alt="Rehive Logo">
  <h1 align="center">Service Stripe</h1>
  <p align="center">A Rehive service to handle stripe payment processing.</p>
</p>

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

The service encapsulates 2 Stripe flows:

1. Checkout setup (payement details collection) : https://stripe.com/docs/payments/checkout/collecting
2. Payment intent creation : https://stripe.com/docs/payments/payment-intents

A summary of the stripe payment processor flow:

1. **CLIENT** -> POST to `/user/sessions/` with a mode of `setup`.
2. **CLIENT** -> Redirect the user to the Stripe interface with returned session id.
3. **SERVER** -> Awaits completetion of the session and updates the session details.
4. **CLIENT** -> POST to `/user/payments/` with an `amount`, `currency`, `payment_method`.
5. **SERVER** -> Initiates a payment using the payment method.
6. **SERVER** -> Awaits completion of the payment and updates its details.
7. **CLIENT** -> Pings the server for updates on the payment and then displays a message.

Between step 6 and 7, an additional 3D Secure step may be required from the **CLIENT**. Whether 3D Secure is required can be checked using the `next_action` object. If it contains `redirect_to_url` as the `type` then 3D Secure confirmation should be triggered by the **CLIENT**.

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
