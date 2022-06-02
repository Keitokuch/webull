import requests
import time
import uuid
import urllib.parse

from .webull import Webull
from . import endpoints

''' Paper support '''
class PaperWebull(Webull):

    def __init__(self):
        super().__init__()

    def get_account(self):
        ''' Get important details of paper account '''
        headers = self.build_req_headers()
        response = requests.get(endpoints.paper_account(self._account_id), headers=headers, timeout=self.timeout)
        return response.json()

    def get_account_id(self):
        ''' Get paper account id: call this before paper account actions'''
        headers = self.build_req_headers()
        response = requests.get(endpoints.paper_account_id(), headers=headers, timeout=self.timeout)
        result = response.json()
        if result is not None and len(result) > 0 and 'id' in result[0]:
            id = result[0]['id']
            self._account_id = id
            return id
        else:
            return None

    def get_current_orders(self):
        ''' Open paper trading orders '''
        return self.get_account()['openOrders']

    def get_history_orders(self, status='Cancelled', count=20):
        headers = self.build_req_headers(include_trade_token=True, include_time=True)
        response = requests.get(endpoints.paper_orders(self._account_id, count) + str(status), headers=headers, timeout=self.timeout)
        return response.json()

    def get_positions(self):
        ''' Current positions in paper trading account. '''
        positions_data = self.get_account()['positions']
        positions = {}
        for item in positions_data:
            symbol = item['ticker']['symbol']
            positions[symbol] = item
        return positions

    def place_order(self, stock=None, tId=None, price=0, action='BUY', orderType='LMT', enforce='GTC', quant=0, outsideRegularTradingHour=True):
        ''' Place a paper account order. '''
        if not tId is None:
            pass
        elif not stock is None:
            tId = self.get_ticker(stock)
        else:
            raise ValueError('Must provide a stock symbol or a stock id')

        headers = self.build_req_headers(include_trade_token=True, include_time=True)

        data = {
            'action': action, #  BUY or SELL
            'lmtPrice': float(price),
            'orderType': orderType, # 'LMT','MKT'
            'outsideRegularTradingHour': outsideRegularTradingHour,
            'quantity': int(quant),
            'serialId': str(uuid.uuid4()),
            'tickerId': tId,
            'timeInForce': enforce  # GTC or DAY
        }

        #Market orders do not support extended hours trading.
        if orderType == 'MKT':
            data['outsideRegularTradingHour'] = False

        response = requests.post(endpoints.paper_place_order(self._account_id, tId), json=data, headers=headers, timeout=self.timeout)
        return response.json()

    def modify_order(self, order, price=0, action='BUY', orderType='LMT', enforce='GTC', quant=0, outsideRegularTradingHour=True):
        ''' Modify a paper account order. '''
        headers = self.build_req_headers()

        data = {
            'action': action, #  BUY or SELL
            'lmtPrice': float(price),
            'orderType':orderType,
            'comboType': 'NORMAL', # 'LMT','MKT'
            'outsideRegularTradingHour': outsideRegularTradingHour,
            'serialId': str(uuid.uuid4()),
            'tickerId': order['ticker']['tickerId'],
            'timeInForce': enforce # GTC or DAY
        }

        if quant == 0 or quant == order['totalQuantity']:
            data['quantity'] = order['totalQuantity']
        else:
            data['quantity'] = int(quant)

        response = requests.post(endpoints.paper_modify_order(self._account_id, order['orderId']), json=data, headers=headers, timeout=self.timeout)
        if response:
            return True
        else:
            print("Modify didn't succeed. {} {}".format(response, response.json()))
            return False

    def cancel_order(self, order_id):
        ''' Cancel a paper account order. '''
        headers = self.build_req_headers()
        response = requests.post(endpoints.paper_cancel_order(self._account_id, order_id), headers=headers, timeout=self.timeout)
        return bool(response)

    def get_social_posts(self, topic, num=100):
        headers = self.build_req_headers()

        response = requests.get(endpoints.social_posts(topic, num), headers=headers, timeout=self.timeout)
        result = response.json()
        return result


    def get_social_home(self, topic, num=100):
        headers = self.build_req_headers()

        response = requests.get(endpoints.social_home(topic, num), headers=headers, timeout=self.timeout)
        result = response.json()
        return result
