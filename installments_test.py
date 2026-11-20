import unittest
from decimal import Decimal
from bot_flows import launch_rows

class Installments(unittest.TestCase):
    def test_exact_cents_for_every_count(self):
        for count in range(2,73):
            for cents in [count,count+1,10001,100000000]:
                rows=launch_rows({'quantidade':count,'modalidade':'Parcelado','valor':cents/100,'data':'2027-01-31','descricao':'Synthetic'})
                self.assertEqual(sum(Decimal(str(r['valor'])) for r in rows),Decimal(cents)/100)
    def test_short_month_and_leap_year_restore_anchor(self):
        for year,feb in [(2027,'28'),(2028,'29')]:
            rows=launch_rows({'quantidade':3,'modalidade':'Parcelado','valor':100,'data':f'{year}-01-31','descricao':'Synthetic'})
            self.assertEqual([r['data'] for r in rows],[f'{year}-01-31',f'{year}-02-{feb}',f'{year}-03-31'])
            self.assertEqual([r['valor'] for r in rows],[33.34,33.33,33.33])

if __name__=='__main__':unittest.main()
