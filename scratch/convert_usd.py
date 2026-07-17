with open('dashboard/app_v2.js', 'r') as f:
    c = f.read()

c = c.replace('€', '$')
c = c.replace('ETH-EUR', 'ETH-USD')
c = c.replace('EUR', 'USD')
c = c.replace('value_eur', 'value_usd')
c = c.replace('price_eur', 'price_usd')
c = c.replace('totalEur', 'totalUsd')

with open('dashboard/app_v2.js', 'w') as f:
    f.write(c)
print("Conversion completed successfully.")
