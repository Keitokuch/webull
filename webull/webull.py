import argparse
import collections
import getpass
import hashlib
import json
import os
import pickle
import requests
import time
import uuid
import urllib.parse

from pathlib import Path
from datetime import datetime, timedelta
from email_validator import validate_email, EmailNotValidError
from pandas import DataFrame, to_datetime
from pytz import timezone

from . import endpoints


class Webull:

    DEFAULT_CREDENTIAL_PATH = Path('webull_credentials.json')

    def __init__(self):
        self._session = requests.session()
        self._headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:99.0) Gecko/20100101 Firefox/99.0',
            'Accept': '*/*',
            'Accept-Encoding': 'gzip, deflate',
            'Content-Type': 'application/json',
            'platform': 'web',
            'app': 'global',
            'appid': 'webull-webapp',
            'ver': '3.39.18',
            'lzone': 'dc_core_r001',
            'device-type': 'Web',
            'did': self._get_did(),
        }

        #sessions
        self._account_id = ''
        self._trade_token = ''
        self._access_token = ''
        self._refresh_token = ''
        self._token_expire = ''
        self._uuid = ''

        #miscellaenous
        self._did = self._get_did()
        self._region_code = 6
        self.zone_var = 'dc_core_r001'
        self.timeout = 15

    def _get_did(self, path=''):
        '''
        Makes a unique device id from a random uuid (uuid.uuid4).
        if the pickle file doesn't exist, this func will generate a random 32 character hex string
        uuid and save it in a pickle file for future use. if the file already exists it will
        load the pickle file to reuse the did. Having a unique did appears to be very important
        for the MQTT web socket protocol

        path: path to did.bin. For example _get_did('cache') will search for cache/did.bin instead.

        :return: hex string of a 32 digit uuid
        '''
        filename = 'did.bin'
        if path:
            filename = os.path.join(path, filename)
        if os.path.exists(filename):
            did = pickle.load(open(filename,'rb'))
        else:
            did = uuid.uuid4().hex
            pickle.dump(did, open(filename, 'wb'))
        return did

    def build_req_headers(self, include_trade_token=False, include_time=False, include_zone_var=True):
        '''
        Build default set of header params
        '''
        headers = self._headers
        headers['did'] = self._did
        headers['access_token'] = self._access_token
        if include_trade_token :
            headers['t_token'] = self._trade_token
        if include_time :
            headers['t_time'] = str(round(time.time() * 1000))
        if include_zone_var :
            headers['lzone'] = self.zone_var
        return headers


    def credential_login(self, credential_path='', refresh=False):
        credential_path = credential_path or Webull.DEFAULT_CREDENTIAL_PATH
        credential_path = Path(credential_path)
        try:
            with open(credential_path, 'r') as f:
                credential_data = json.load(f)
        except OSError as e:
            print(f"Failed to open {credential_path}: {e}")
            return None
        self._refresh_token = credential_data['refreshToken']
        self._access_token = credential_data['accessToken']
        self._token_expire = credential_data['tokenExpireTime']
        self._uuid = credential_data['uuid']
        self._credential_data = credential_data
        self.get_account_id()
        if refresh:
            self._credential_data = self.refresh_login()
            self.save_credential(path=credential_path)
        return credential_data


    def save_credential(self, path='', credential_data=None):
        credential_path = path or Webull.DEFAULT_CREDENTIAL_PATH
        credential_data = credential_data or self._credential_data
        self._credential_data = credential_data
        with open(credential_path, 'w') as f:
            json.dump(credential_data, f)
        return credential_data


    def login(self, username='', password='', device_name='', mfa='', question_id='', question_answer='', credential_path='', save_token=False, token_path=None):
        '''
        Login with email or phone number

        phone numbers must be a str in the following form
        US '+1-XXXXXXX'
        CH '+86-XXXXXXXXXXX'
        '''

        if credential_path:
            self.credential_login(credential_path)

        if not username or not password:
            return self.credential_login()

        # with webull md5 hash salted
        password = ('wl_app-a&b@!423^' + password).encode('utf-8')
        md5_hash = hashlib.md5(password)

        account_type = self.get_account_type(username)

        if device_name == '' :
            device_name = 'default_string'

        data = {
            'account': username,
            'accountType': str(account_type),
            'deviceId': self._did,
            'deviceName': device_name,
            'grade': 1,
            'pwd': md5_hash.hexdigest(),
            'regionId': self._region_code
        }

        if mfa != '' :
            data['extInfo'] = {
                'codeAccountType': account_type,
                'verificationCode': mfa
            }
            headers = self.build_req_headers()
        else :
            headers = self._headers

        if question_id != '' and question_answer != '' :
            data['accessQuestions'] = '[{"questionId":"' + str(question_id) + '", "answer":"' + str(question_answer) + '"}]'

        response = requests.post(endpoints.login(), json=data, headers=headers, timeout=self.timeout)
        result = response.json()
        if 'accessToken' in result :
            self._access_token = result['accessToken']
            self._refresh_token = result['refreshToken']
            self._token_expire = result['tokenExpireTime']
            self._uuid = result['uuid']
            self._account_id = self.get_account_id()
            self._credential_data = result
            if save_token:
                self._save_token(result, token_path)
        return result

    def get_mfa(self, username='') :
        account_type = self.get_account_type(username)

        data = {'account': str(username),
                'accountType': str(account_type),
                'codeType': int(5)}

        response = requests.post(endpoints.get_mfa(), json=data, headers=self._headers, timeout=self.timeout)
        # data = response.json()

        if response.status_code == 200 :
            return True
        else :
            return False

    def check_mfa(self, username='', mfa='') :
        account_type = self.get_account_type(username)

        data = {'account': str(username),
                'accountType': str(account_type),
                'code': str(mfa),
                'codeType': int(5)}

        response = requests.post(endpoints.check_mfa(), json=data, headers=self._headers, timeout=self.timeout)
        data = response.json()

        return data

    def get_security(self, username='') :
        account_type = self.get_account_type(username)
        username = urllib.parse.quote(username)

        # seems like webull has a bug/stability issue here:
        time = datetime.now().timestamp() * 1000
        response = requests.get(endpoints.get_security(username, account_type, self._region_code, 'PRODUCT_LOGIN', time, 0), headers=self._headers, timeout=self.timeout)
        data = response.json()
        if len(data) == 0 :
            response = requests.get(endpoints.get_security(username, account_type, self._region_code, 'PRODUCT_LOGIN', time, 1), headers=self._headers, timeout=self.timeout)
            data = response.json()

        return data

    def next_security(self, username='') :
        account_type = self.get_account_type(username)
        username = urllib.parse.quote(username)

        # seems like webull has a bug/stability issue here:
        time = datetime.now().timestamp() * 1000
        response = requests.get(endpoints.next_security(username, account_type, self._region_code, 'PRODUCT_LOGIN', time, 0), headers=self._headers, timeout=self.timeout)
        data = response.json()
        if len(data) == 0 :
            response = requests.get(endpoints.next_security(username, account_type, self._region_code, 'PRODUCT_LOGIN', time, 1), headers=self._headers, timeout=self.timeout)
            print(response)
            data = response.json()

        return data

    def check_security(self, username='', question_id='', question_answer='') :
        account_type = self.get_account_type(username)

        data = {'account': str(username),
                'accountType': str(account_type),
                'answerList': [{'questionId': str(question_id), 'answer': str(question_answer)}],
                'event': 'PRODUCT_LOGIN'}

        response = requests.post(endpoints.check_security(), json=data, headers=self._headers, timeout=self.timeout)
        data = response.json()

        return data

    def login_prompt(self):
        '''
        End login session
        '''
        uname = input('Enter Webull Username:')
        pwd = getpass.getpass('Enter Webull Password:')
        self.trade_pin = getpass.getpass('Enter 6 digit Webull Trade PIN:')
        self.login(uname, pwd)
        return self.get_trade_token(self.trade_pin)

    def trade_prompt(self):
        self.trade_pin = getpass.getpass('Enter 6 digit Webull Trade PIN:')
        return self.get_trade_token(self.trade_pin)

    def logout(self):
        '''
        End login session
        '''
        headers = self.build_req_headers()
        response = requests.get(endpoints.logout(), headers=headers, timeout=self.timeout)
        return response.status_code

    def api_login(self, access_token='', refresh_token='', token_expire='', uuid='', mfa=''):
        self._access_token = access_token
        self._refresh_token = refresh_token
        self._token_expire = token_expire
        self._uuid = uuid
        self._account_id = self.get_account_id()

    def refresh_login(self, save_token=False, token_path=None):
        '''
        Refresh login token
        '''
        headers = self.build_req_headers()
        data = {'refreshToken': self._refresh_token}

        response = requests.post(endpoints.refresh_login() + self._refresh_token, json=data, headers=headers, timeout=self.timeout)
        result = response.json()
        if 'accessToken' in result and result['accessToken'] != '' and result['refreshToken'] != '' and result['tokenExpireTime'] != '':
            self._access_token = result['accessToken']
            self._refresh_token = result['refreshToken']
            self._token_expire = result['tokenExpireTime']
            result['uuid'] = self._uuid
            if save_token:
                self._save_token(result, token_path)
        return result

    def _save_token(self, token=None, path=None):
        '''
        save login token to webull_credentials.json
        '''
        path = path or Webull.DEFAULT_CREDENTIAL_PATH
        with open(path, 'w') as f:
            json.dump(token, f)

    def get_detail(self):
        '''
        get some contact details of your account name, email/phone, region, avatar...etc
        '''
        headers = self.build_req_headers()

        response = requests.get(endpoints.user(), headers=headers, timeout=self.timeout)
        result = response.json()

        return result

    def get_account_id(self, id=0):
        '''
        get account id
        call account id before trade actions
        '''
        headers = self.build_req_headers()

        response = requests.get(endpoints.account_id(), headers=headers, timeout=self.timeout)
        result = response.json()
        if result['success'] and len(result['data']) > 0 :
            self.zone_var = str(result['data'][int(id)]['rzone'])
            self._account_id = str(result['data'][int(id)]['secAccountId'])
            return self._account_id
        else:
            return None

    def get_account(self):
        '''
        get important details of account, positions, portfolio stance...etc
        '''
        headers = self.build_req_headers()
        response = requests.get(endpoints.account(self._account_id), headers=headers, timeout=self.timeout)
        result = response.json()
        return result

    def get_positions(self):
        '''
        output standing positions of stocks
        '''
        data = self.get_account()
        return data['positions']

    def get_portfolio(self):
        '''
        output numbers of portfolio
        '''
        data = self.get_account()
        output = {}
        for item in data['accountMembers']:
            output[item['key']] = item['value']
        return output

    def get_activities(self, index=1, size=500) :
        '''
        Activities including transfers, trades and dividends
        '''
        headers = self.build_req_headers(include_trade_token=True, include_time=True)
        data = {'pageIndex': index,
                'pageSize': size}
        response = requests.post(endpoints.account_activities(self._account_id), json=data, headers=headers, timeout=self.timeout)
        return response.json()

    def get_current_orders(self) :
        '''
        Get open/standing orders
        '''
        data = self.get_account()
        return data['openOrders']

    def get_history_orders(self, status='All', count=20):
        '''
        Historical orders, can be cancelled or filled
        status = Cancelled / Filled / Working / Partially Filled / Pending / Failed / All
        '''
        headers = self.build_req_headers(include_trade_token=True, include_time=True)
        response = requests.get(endpoints.orders(self._account_id, count) + str(status), headers=headers, timeout=self.timeout)
        return response.json()

    def get_trade_token(self, password=''):
        '''
        Trading related
        authorize trade, must be done before trade action
        '''
        headers = self.build_req_headers()

        # with webull md5 hash salted
        password = ('wl_app-a&b@!423^' + password).encode('utf-8')
        md5_hash = hashlib.md5(password)
        data = {'pwd': md5_hash.hexdigest()}

        response = requests.post(endpoints.trade_token(), json=data, headers=headers, timeout=self.timeout)
        result = response.json()
        if 'tradeToken' in result :
            self._trade_token = result['tradeToken']
            return True
        else:
            return False

    def get_ticker(self, stock=''):
        '''
        Lookup ticker_id
        Ticker issue, will attempt to find an exact match, if none is found, match the first one
        '''
        headers = self.build_req_headers()
        ticker_id = 0
        if stock and isinstance(stock, str):
            response = requests.get(endpoints.stock_id(stock, self._region_code), headers=headers, timeout=self.timeout)
            result = response.json()
            if result.get('data') :
                for item in result['data'] : # implies multiple tickers, but only assigns last one?
                    if 'symbol' in item and item['symbol'] == stock :
                        ticker_id = item['tickerId']
                        break
                    elif 'disSymbol' in item and item['disSymbol'] == stock :
                        ticker_id = item['tickerId']
                        break
                if ticker_id == 0 :
                    ticker_id = result['data'][0]['tickerId']
            else:
                raise ValueError('TickerId could not be found for stock {}'.format(stock))
        else:
            raise ValueError('Stock symbol is required')
        return ticker_id

    '''
    Actions related to stock
    '''
    def get_quote(self, stock=None, tId=None):
        '''
        get price quote
        tId: ticker ID str
        '''
        headers = self.build_req_headers()
        if not stock and not tId:
            raise ValueError('Must provide a stock symbol or a stock id')

        if stock:
            try:
                tId = str(self.get_ticker(stock))
            except ValueError as _e:
                raise ValueError("Could not find ticker for stock {}".format(stock))
        response = requests.get(endpoints.quotes(tId), headers=headers, timeout=self.timeout)
        result = response.json()
        return result

    def place_order(self, stock=None, tId=None, price=0, action='BUY', orderType='LMT', enforce='GTC', quant=0, outsideRegularTradingHour=True, stpPrice=None, trial_value=0, trial_type='DOLLAR'):
        '''
        Place an order

        price: float (LMT / STP LMT Only)
        action: BUY / SELL / SHORT
        ordertype : LMT / MKT / STP / STP LMT / STP TRAIL
        timeinforce:  GTC / DAY / IOC
        outsideRegularTradingHour: True / False
        stpPrice: float (STP / STP LMT Only)
        trial_value: float (STP TRIAL Only)
        trial_type: DOLLAR / PERCENTAGE (STP TRIAL Only)
        '''
        if not tId is None:
            pass
        elif not stock is None:
            tId = self.get_ticker(stock)
        else:
            raise ValueError('Must provide a stock symbol or a stock id')

        headers = self.build_req_headers(include_trade_token=True, include_time=True)
        data = {
            'action': action,
            'comboType': 'NORMAL',
            'orderType': orderType,
            'outsideRegularTradingHour': outsideRegularTradingHour,
            'quantity': int(quant),
            'serialId': str(uuid.uuid4()),
            'tickerId': tId,
            'timeInForce': enforce
        }

        # Market orders do not support extended hours trading.
        if orderType == 'MKT' :
            data['outsideRegularTradingHour'] = False
        elif orderType == 'LMT':
            data['lmtPrice'] = float(price)
        elif orderType == 'STP' :
            data['auxPrice'] = float(stpPrice)
        elif orderType == 'STP LMT' :
            data['lmtPrice'] = float(price)
            data['auxPrice'] = float(stpPrice)
        elif orderType == 'STP TRAIL' :
            data['trailingStopStep'] = float(trial_value)
            data['trailingType'] = str(trial_type)

        response = requests.post(endpoints.place_orders(self._account_id), json=data, headers=headers, timeout=self.timeout)
        return response.json()

    def modify_order(self, order=None, order_id=0, stock=None, tId=None, price=0, action=None, orderType=None, enforce=None, quant=0, outsideRegularTradingHour=None):
        '''
        Modify an order
        order_id: order_id
        action: BUY / SELL
        ordertype : LMT / MKT / STP / STP LMT / STP TRAIL
        timeinforce:  GTC / DAY / IOC
        outsideRegularTradingHour: True / False
        '''
        if not order and not order_id:
            raise ValueError('Must provide an order or order_id')

        headers = self.build_req_headers(include_trade_token=True, include_time=True)

        modifiedAction = action or order['action']
        modifiedLmtPrice = float(price or order['lmtPrice'])
        modifiedOrderType = orderType or order['orderType']
        modifiedOutsideRegularTradingHour = outsideRegularTradingHour if type(outsideRegularTradingHour) == bool else order['outsideRegularTradingHour']
        modifiedEnforce = enforce or order['timeInForce']
        modifiedQuant = int(quant or order['quantity'])
        if not tId is None:
            pass
        elif not stock is None:
            tId = self.get_ticker(stock)
        else :
            tId = order['ticker']['tickerId']
        order_id = order_id or order['orderId']

        data = {
            'action': modifiedAction,
            'lmtPrice': modifiedLmtPrice,
            'orderType': modifiedOrderType,
            'quantity': modifiedQuant,
            'comboType': 'NORMAL',
            'outsideRegularTradingHour': modifiedOutsideRegularTradingHour,
            'serialId': str(uuid.uuid4()),
            'orderId': order_id,
            'tickerId': tId,
            'timeInForce': modifiedEnforce
        }
        #Market orders do not support extended hours trading.
        if data['orderType'] == 'MKT':
            data['outsideRegularTradingHour'] = False

        response = requests.post(endpoints.modify_order(self._account_id, order_id), json=data, headers=headers, timeout=self.timeout)

        return response.json()

    def cancel_order(self, order_id=''):
        '''
        Cancel an order
        '''
        headers = self.build_req_headers(include_trade_token=True, include_time=True)
        data = {}
        response = requests.post(endpoints.cancel_order(self._account_id) + str(order_id) + '/' + str(uuid.uuid4()), json=data, headers=headers, timeout=self.timeout)
        result = response.json()
        return result['success']

    def place_order_otoco(self, stock='', price='', stop_loss_price='', limit_profit_price='', time_in_force='DAY', quant=0) :
        '''
        OTOCO: One-triggers-a-one-cancels-the-others, aka Bracket Ordering
        Submit a buy order, its fill will trigger sell order placement. If one sell fills, it will cancel the other
         sell
        '''
        headers = self.build_req_headers(include_trade_token=False, include_time=True)
        data1 = {
            'newOrders': [
                {'orderType': 'LMT', 'timeInForce': time_in_force, 'quantity': int(quant),
                 'outsideRegularTradingHour': False, 'action': 'BUY', 'tickerId': self.get_ticker(stock),
                 'lmtPrice': float(price), 'comboType': 'MASTER'},
                {'orderType': 'STP', 'timeInForce': time_in_force, 'quantity': int(quant),
                 'outsideRegularTradingHour': False, 'action': 'SELL', 'tickerId': self.get_ticker(stock),
                 'auxPrice': float(stop_loss_price), 'comboType': 'STOP_LOSS'},
                {'orderType': 'LMT', 'timeInForce': time_in_force, 'quantity': int(quant),
                 'outsideRegularTradingHour': False, 'action': 'SELL', 'tickerId': self.get_ticker(stock),
                 'lmtPrice': float(limit_profit_price), 'comboType': 'STOP_PROFIT'}
            ]
        }

        response1 = requests.post(endpoints.check_otoco_orders(self._account_id), json=data1, headers=headers, timeout=self.timeout)
        result1 = response1.json()

        if result1['forward'] :
            data2 = {'newOrders': [
                            {'orderType': 'LMT', 'timeInForce': time_in_force, 'quantity': int(quant),
                             'outsideRegularTradingHour': False, 'action': 'BUY', 'tickerId': self.get_ticker(stock),
                             'lmtPrice': float(price), 'comboType': 'MASTER', 'serialId': str(uuid.uuid4())},
                            {'orderType': 'STP', 'timeInForce': time_in_force, 'quantity': int(quant),
                             'outsideRegularTradingHour': False, 'action': 'SELL', 'tickerId': self.get_ticker(stock),
                             'auxPrice': float(stop_loss_price), 'comboType': 'STOP_LOSS', 'serialId': str(uuid.uuid4())},
                            {'orderType': 'LMT', 'timeInForce': time_in_force, 'quantity': int(quant),
                             'outsideRegularTradingHour': False, 'action': 'SELL', 'tickerId': self.get_ticker(stock),
                             'lmtPrice': float(limit_profit_price), 'comboType': 'STOP_PROFIT', 'serialId': str(uuid.uuid4())}],
                            'serialId': str(uuid.uuid4())
                    }

            response2 = requests.post(endpoints.place_otoco_orders(self._account_id), json=data2, headers=headers, timeout=self.timeout)

            # print('Resp 2: {}'.format(response2))
            return response2.json()
        else:
            print(result1['checkResultList'][0]['code'])
            print(result1['checkResultList'][0]['msg'])
            return False

    def modify_order_otoco(self, order_id1='', order_id2='', order_id3='', stock='', price='', stop_loss_price='', limit_profit_price='', time_in_force='DAY', quant=0) :
        '''
        OTOCO: One-triggers-a-one-cancels-the-others, aka Bracket Ordering
        Submit a buy order, its fill will trigger sell order placement. If one sell fills, it will cancel the other
         sell
        '''
        headers = self.build_req_headers(include_trade_token=False, include_time=True)

        data = {'modifyOrders': [
                        {'orderType': 'LMT', 'timeInForce': time_in_force, 'quantity': int(quant), 'orderId': str(order_id1),
                         'outsideRegularTradingHour': False, 'action': 'BUY', 'tickerId': self.get_ticker(stock),
                         'lmtPrice': float(price), 'comboType': 'MASTER', 'serialId': str(uuid.uuid4())},
                        {'orderType': 'STP', 'timeInForce': time_in_force, 'quantity': int(quant), 'orderId': str(order_id2),
                         'outsideRegularTradingHour': False, 'action': 'SELL', 'tickerId': self.get_ticker(stock),
                         'auxPrice': float(stop_loss_price), 'comboType': 'STOP_LOSS', 'serialId': str(uuid.uuid4())},
                        {'orderType': 'LMT', 'timeInForce': time_in_force, 'quantity': int(quant), 'orderId': str(order_id3),
                         'outsideRegularTradingHour': False, 'action': 'SELL', 'tickerId': self.get_ticker(stock),
                         'lmtPrice': float(limit_profit_price), 'comboType': 'STOP_PROFIT', 'serialId': str(uuid.uuid4())}],
                        'serialId': str(uuid.uuid4())
                }

        response = requests.post(endpoints.modify_otoco_orders(self._account_id), json=data, headers=headers, timeout=self.timeout)

        # print('Resp: {}'.format(response))
        return response.json()

    def cancel_order_otoco(self, combo_id=''):
        '''
        Retract an otoco order. Cancelling the MASTER order_id cancels the sub orders.
        '''
        headers = self.build_req_headers(include_trade_token=True, include_time=True)
        # data = { 'serialId': str(uuid.uuid4()), 'cancelOrders': [str(order_id)]}
        data = {}
        response = requests.post(endpoints.cancel_otoco_orders(self._account_id, combo_id), json=data, headers=headers, timeout=self.timeout)
        return response.json()

    '''
    Actions related to cryptos
    '''
    def place_order_crypto(self, stock=None, tId=None, price=0, action='BUY', orderType='LMT', enforce='DAY', entrust_type='QTY', quant=0, outsideRegularTradingHour=False) :
        '''
        Place Crypto order
        price: Limit order entry price
        quant: dollar amount to buy/sell when entrust_type is CASH else the decimal or fractional amount of shares to buy
        action: BUY / SELL
        entrust_type: CASH / QTY
        ordertype : LMT / MKT
        timeinforce:  DAY
        outsideRegularTradingHour: True / False
        '''
        if not tId is None:
            pass
        elif not stock is None:
            tId = self.get_ticker(stock)
        else:
            raise ValueError('Must provide a stock symbol or a stock id')

        headers = self.build_req_headers(include_trade_token=True, include_time=True)
        data = {
            'action': action,
            'assetType': 'crypto',
            'comboType': 'NORMAL',
            'entrustType': entrust_type,
            'lmtPrice': str(price),
            'orderType': orderType,
            'outsideRegularTradingHour': outsideRegularTradingHour,
            'quantity': str(quant),
            'serialId': str(uuid.uuid4()),
            'tickerId': tId,
            'timeInForce': enforce
        }

        response = requests.post(endpoints.place_orders(self._account_id), json=data, headers=headers, timeout=self.timeout)
        return response.json()

    '''
    Actions related to options
    '''
    def get_option_quote(self, stock=None, tId=None, optionId=None):
        '''
        get option quote
        '''
        if not stock and not tId:
            raise ValueError('Must provide a stock symbol or a stock id')

        if stock:
            try:
                tId = str(self.get_ticker(stock))
            except ValueError as _e:
                raise ValueError("Could not find ticker for stock {}".format(stock))
        headers = self.build_req_headers()
        params = {'tickerId': tId, 'derivativeIds': optionId}
        return requests.get(endpoints.option_quotes(), params=params, headers=headers, timeout=self.timeout).json()

    def get_options_expiration_dates(self, stock=None, count=-1):
        '''
        returns a list of options expiration dates
        '''
        headers = self.build_req_headers()
        data = {'count': count}
        return requests.get(endpoints.options_exp_date(self.get_ticker(stock)), params=data, headers=headers, timeout=self.timeout).json()['expireDateList']

    def get_options(self, stock=None, count=-1, includeWeekly=1, direction='all', expireDate=None, queryAll=0):
        '''
        get options and returns a dict of options contracts
        params:
            stock: symbol
            count: -1
            includeWeekly: 0 or 1
            direction: all, calls, puts
            expireDate: contract expire date
            queryAll: 0
        '''
        headers = self.build_req_headers()
        # get next closet expiredate if none is provided
        if not expireDate:
            dates = self.get_options_expiration_dates(stock)
            # ensure we don't provide an option that has < 1 day to expire
            for d in dates:
                if d['days'] > 0:
                    expireDate = d['date']
                    break

        params = {'count': count,
                  'includeWeekly': includeWeekly,
                  'direction': direction,
                  'expireDate': expireDate,
                  'unSymbol': stock,
                  'queryAll': queryAll}

        data = requests.get(endpoints.options(self.get_ticker(stock)), params=params, headers=headers, timeout=self.timeout).json()

        return data['data']

    def get_options_by_strike_and_expire_date(self, stock=None, expireDate=None, strike=None, direction='all'):
        '''
        get a list of options contracts by expire date and strike price
        strike: string
        '''

        opts = self.get_options(stock=stock, expireDate=expireDate, direction=direction)
        return [c for c in opts if c['strikePrice'] == strike]

    def place_order_option(self, optionId=None, lmtPrice=None, stpPrice=None, action=None, orderType='LMT', enforce='DAY', quant=0):
        '''
        create buy / sell order
        stock: string
        lmtPrice: float
        stpPrice: float
        action: string BUY / SELL
        optionId: string
        orderType: MKT / LMT / STP / STP LMT
        enforce: GTC / DAY
        quant: int
        '''
        headers = self.build_req_headers(include_trade_token=True, include_time=True)
        data = {
            'orderType': orderType,
            'serialId': str(uuid.uuid4()),
            'timeInForce': enforce,
            'orders': [{'quantity': int(quant), 'action': action, 'tickerId': int(optionId), 'tickerType': 'OPTION'}],
        }

        if orderType == 'LMT' and lmtPrice :
            data['lmtPrice'] = float(lmtPrice)
        elif orderType == 'STP' and stpPrice :
            data['auxPrice'] = float(stpPrice)
        elif orderType == 'STP LMT' and lmtPrice and stpPrice :
            data['lmtPrice'] = float(lmtPrice)
            data['auxPrice'] = float(stpPrice)

        response = requests.post(endpoints.place_option_orders(self._account_id), json=data, headers=headers, timeout=self.timeout)
        if response.status_code != 200:
            raise Exception('place_option_order failed', response.status_code, response.reason)
        return response.json()

    def modify_order_option(self, order=None, lmtPrice=None, stpPrice=None, enforce=None, quant=0):
        '''
        order: dict from get_current_orders
        stpPrice: float
        lmtPrice: float
        enforce: GTC / DAY
        quant: int
        '''
        headers = self.build_req_headers(include_trade_token=True, include_time=True)
        data = {
            'comboId': order['comboId'],
            'orderType': order['orderType'],
            'timeInForce': enforce or order['timeInForce'],
            'serialId': str(uuid.uuid4()),
            'orders': [{'quantity': quant or order['totalQuantity'],
                        'action': order['action'],
                        'tickerId': order['ticker']['tickerId'],
                        'tickerType': 'OPTION',
                        'orderId': order['orderId']}]
        }

        if order['orderType'] == 'LMT' and (lmtPrice or order.get('lmtPrice')):
            data['lmtPrice'] = lmtPrice or order['lmtPrice']
        elif order['orderType'] == 'STP' and (stpPrice or order.get('auxPrice')):
            data['auxPrice'] = stpPrice or order['auxPrice']
        elif order['orderType'] == 'STP LMT' and (stpPrice or order.get('auxPrice')) and (lmtPrice or order.get('lmtPrice')):
            data['auxPrice'] = stpPrice or order['auxPrice']
            data['lmtPrice'] = lmtPrice or order['lmtPrice']

        response = requests.post(endpoints.replace_option_orders(self._account_id), json=data, headers=headers, timeout=self.timeout)
        if response.status_code != 200:
            raise Exception('replace_option_order failed', response.status_code, response.reason)
        return True

    def cancel_all_orders(self):
        '''
        Cancels all open (aka 'working') orders
        '''
        open_orders = self.get_current_orders()
        for order in open_orders:
            self.cancel_order(order['orderId'])

    def get_tradable(self, stock='') :
        '''
        get if stock is tradable
        '''
        headers = self.build_req_headers()
        response = requests.get(endpoints.is_tradable(self.get_ticker(stock)), headers=headers, timeout=self.timeout)

        return response.json()

    def alerts_list(self) :
        '''
        Get alerts
        '''
        headers = self.build_req_headers()

        response = requests.get(endpoints.list_alerts(), headers=headers, timeout=self.timeout)
        result = response.json()
        if 'data' in result:
            return result.get('data', [])
        else:
            return None

    def alerts_remove(self, alert=None, priceAlert=True, smartAlert=True):
        '''
        remove alert
        alert is retrieved from alert_list
        '''
        headers = self.build_req_headers()

        if alert.get('tickerWarning') and priceAlert:
            alert['tickerWarning']['remove'] = True
            alert['warningInput'] = alert['tickerWarning']

        if alert.get('eventWarning') and smartAlert:
            alert['eventWarning']['remove'] = True
            for rule in alert['eventWarning']['rules']:
                rule['active'] = 'off'
            alert['eventWarningInput'] = alert['eventWarning']

        response = requests.post(endpoints.remove_alert(), json=alert, headers=headers, timeout=self.timeout)
        if response.status_code != 200:
            raise Exception('alerts_remove failed', response.status_code, response.reason)
        return True

    def alerts_add(self, stock=None, frequency=1, interval=1, priceRules=[], smartRules=[]):
        '''
        add price/percent/volume alert
        frequency: 1 is once a day, 2 is once a minute
        interval: 1 is once, 0 is repeating
        priceRules: list of dicts with below attributes per alert
            field: price , percent , volume
            type: price (above/below), percent (above/below), volume (vol in thousands)
            value: price, percent, volume amount
            remark: comment
        rules example:
        priceRules = [{'field': 'price', 'type': 'above', 'value': '900.00', 'remark': 'above'}, {'field': 'price', 'type': 'below',
             'value': '900.00', 'remark': 'below'}]
        smartRules = [{'type':'earnPre','active':'on'},{'type':'fastUp','active':'on'},{'type':'fastDown','active':'on'},
            {'type':'week52Up','active':'on'},{'type':'week52Down','active':'on'},{'type':'day5Down','active':'on'}]
        '''
        headers = self.build_req_headers()

        rule_keys = ['value', 'field', 'remark', 'type', 'active']
        for line, rule in enumerate(priceRules, start=1):
            for key in rule:
                if key not in rule_keys:
                    raise Exception('malformed price alert priceRules found.')
            rule['alertRuleKey'] = line
            rule['active'] = 'on'

        alert_keys = ['earnPre', 'fastUp', 'fastDown', 'week52Up', 'week52Down', 'day5Up', 'day10Up', 'day20Up', 'day5Down', 'day10Down', 'day20Down']
        for rule in smartRules:
            if rule['type'] not in alert_keys:
                raise Exception('malformed smart alert smartRules found.')

        try:
            stock_data = self.get_tradable(stock)['data'][0]
            data = {
                'regionId': stock_data['regionId'],
                'tickerType': stock_data['type'],
                'tickerId': stock_data['tickerId'],
                'tickerSymbol': stock,
                'disSymbol': stock,
                'tinyName': stock_data['name'],
                'tickerName': stock_data['name'],
                'exchangeCode': stock_data['exchangeCode'],
                'showCode': stock_data['disExchangeCode'],
                'disExchangeCode': stock_data['disExchangeCode'],
                'eventWarningInput': {
                    'tickerId': stock_data['tickerId'],
                    'rules': smartRules,
                    'remove': False,
                    'del': False
                },
                'warningInput': {
                    'warningFrequency': frequency,
                    'warningInterval': interval,
                    'rules': priceRules,
                    'tickerId': stock_data['tickerId']
                }
            }
        except Exception as e:
            print(f'failed to build alerts_add payload data. error: {e}')

        response = requests.post(endpoints.add_alert(), json=data, headers=headers, timeout=self.timeout)
        if response.status_code != 200:
            raise Exception('alerts_add failed', response.status_code, response.reason)
        return True

    def active_gainer_loser(self, direction='gainer', rank_type='afterMarket', count=50) :
          '''
          gets gainer / loser / active stocks sorted by change
          direction: gainer / loser / active
          rank_type: preMarket / afterMarket / 5min / 1d / 5d / 1m / 3m / 52w (gainer/loser)
                     volume / turnoverRatio / range (active)
          '''
          headers = self.build_req_headers()

          response = requests.get(endpoints.active_gainers_losers(direction, self._region_code, rank_type, count), headers=headers, timeout=self.timeout)
          result = response.json()

          return result

    def run_screener(self, region=None, price_lte=None, price_gte=None, pct_chg_gte=None, pct_chg_lte=None, sort=None,
                     sort_dir=None, vol_lte=None, vol_gte=None):
        '''
        Notice the fact that endpoints are reversed on lte and gte, but this function makes it work correctly
        Also screeners are not sent by name, just the parameters are sent
        example: run_screener( price_lte=.10, price_gte=5, pct_chg_lte=.035, pct_chg_gte=.51)
        just a start, add more as you need it
        '''

        jdict = collections.defaultdict(dict)
        jdict['fetch'] = 200
        jdict['rules'] = collections.defaultdict(str)
        jdict['sort'] = collections.defaultdict(str)
        jdict['attach'] = {'hkexPrivilege': 'true'}  #unknown meaning, was in network trace

        jdict['rules']['wlas.screener.rule.region'] = 'securities.region.name.6'
        if not price_lte is None and not price_gte is None:
            # lte and gte are backwards
            jdict['rules']['wlas.screener.rule.price'] = 'gte=' + str(price_lte) + '&lte=' + str(price_gte)

        if not vol_lte is None and not vol_gte is None:
            # lte and gte are backwards
            jdict['rules']['wlas.screener.rule.volume'] = 'gte=' + str(vol_lte) + '&lte=' + str(vol_gte)

        if not pct_chg_lte is None and not pct_chg_gte is None:
            # lte and gte are backwards
            jdict['rules']['wlas.screener.rule.changeRatio'] = 'gte=' + str(pct_chg_lte) + '&lte=' + str(pct_chg_gte)

        if sort is None:
            jdict['sort']['rule'] = 'wlas.screener.rule.price'
        if sort_dir is None:
            jdict['sort']['desc'] = 'true'

        # jdict = self._ddict2dict(jdict)
        response = requests.post(endpoints.screener(), json=jdict, timeout=self.timeout)
        result = response.json()
        return result

    def get_analysis(self, stock=None):
        '''
        get analysis info and returns a dict of analysis ratings
        '''
        headers = self.build_req_headers()
        return requests.get(endpoints.analysis(self.get_ticker(stock)), headers=headers, timeout=self.timeout).json()

    def get_capital_flow(self, stock=None, tId=None, show_hist=True):
        '''
        get capital flow
        :param stock:
        :param tId:
        :param show_hist:
        :return: list of capital flow
        '''
        headers = self.build_req_headers()
        if not tId is None:
            pass
        elif not stock is None:
            tId = self.get_ticker(stock)
        else:
            raise ValueError('Must provide a stock symbol or a stock id')
        return requests.get(endpoints.analysis_capital_flow(tId, show_hist), headers=headers, timeout=self.timeout).json()

    def get_etf_holding(self, stock=None, tId=None, has_num=0, count=50):
        '''
        get ETF holdings by stock
        :param stock:
        :param tId:
        :param has_num:
        :param count:
        :return: list of ETF holdings
        '''
        headers = self.build_req_headers()
        if not tId is None:
            pass
        elif not stock is None:
            tId = self.get_ticker(stock)
        else:
            raise ValueError('Must provide a stock symbol or a stock id')
        return requests.get(endpoints.analysis_etf_holding(tId, has_num, count), headers=headers, timeout=self.timeout).json()

    def get_institutional_holding(self, stock=None, tId=None):
        '''
        get institutional holdings
        :param stock:
        :param tId:
        :return: list of institutional holdings
        '''
        headers = self.build_req_headers()
        if not tId is None:
            pass
        elif not stock is None:
            tId = self.get_ticker(stock)
        else:
            raise ValueError('Must provide a stock symbol or a stock id')
        return requests.get(endpoints.analysis_institutional_holding(tId), headers=headers, timeout=self.timeout).json()

    def get_short_interest(self, stock=None, tId=None):
        '''
        get short interest
        :param stock:
        :param tId:
        :return: list of short interest
        '''
        headers = self.build_req_headers()
        if not tId is None:
            pass
        elif not stock is None:
            tId = self.get_ticker(stock)
        else:
            raise ValueError('Must provide a stock symbol or a stock id')
        return requests.get(endpoints.analysis_shortinterest(tId), headers=headers, timeout=self.timeout).json()

    def get_financials(self, stock=None):
        '''
        get financials info and returns a dict of financial info
        '''
        headers = self.build_req_headers()
        return requests.get(endpoints.fundamentals(self.get_ticker(stock)), headers=headers, timeout=self.timeout).json()

    def get_news(self, stock=None, tId=None, Id=0, items=20):
        '''
        get news and returns a list of articles
        params:
            Id: 0 is latest news article
            items: number of articles to return
        '''
        headers = self.build_req_headers()
        if not tId is None:
            pass
        elif not stock is None:
            tId = self.get_ticker(stock)
        else:
            raise ValueError('Must provide a stock symbol or a stock id')
        return requests.get(endpoints.news(tId, Id, items), headers=headers, timeout=self.timeout).json()

    def get_bars(self, stock=None, tId=None, interval='m1', count=1, extendTrading=0, timeStamp=None):
        '''
        get bars returns a pandas dataframe
        params:
            interval: m1, m5, m15, m30, h1, h2, h4, d1, w1
            count: number of bars to return
            extendTrading: change to 1 for pre-market and afterhours bars
            timeStamp: If epoc timestamp is provided, return bar count up to timestamp. If not set default to current time.
        '''
        headers = self.build_req_headers()
        if not tId is None:
            pass
        elif not stock is None:
            tId = self.get_ticker(stock)
        else:
            raise ValueError('Must provide a stock symbol or a stock id')

        params = {'type': interval, 'count': count, 'extendTrading': extendTrading, 'timestamp': timeStamp}
        df = DataFrame(columns=['open', 'high', 'low', 'close', 'volume', 'vwap'])
        df.index.name = 'timestamp'
        response = requests.get(endpoints.bars(tId), params=params, headers=headers, timeout=self.timeout)
        result = response.json()
        time_zone = timezone(result[0]['timeZone'])
        for row in result[0]['data']:
            row = row.split(',')
            row = ['0' if value == 'null' else value for value in row]
            data = {
                'open': float(row[1]),
                'high': float(row[3]),
                'low': float(row[4]),
                'close': float(row[2]),
                'volume': float(row[6]),
                'vwap': float(row[7])
            }
            #convert to a panda datetime64 which has extra features like floor and resample
            df.loc[to_datetime(datetime.fromtimestamp(int(row[0])).astimezone(time_zone))] = data
        return df.iloc[::-1]

    def get_bars_crypto(self, stock=None, tId=None, interval='m1', count=1, extendTrading=0, timeStamp=None):
        '''
        get bars returns a pandas dataframe
        params:
            interval: m1, m5, m15, m30, h1, h2, h4, d1, w1
            count: number of bars to return
            extendTrading: change to 1 for pre-market and afterhours bars
            timeStamp: If epoc timestamp is provided, return bar count up to timestamp. If not set default to current time.
        '''
        headers = self.build_req_headers()
        if not tId is None:
            pass
        elif not stock is None:
            tId = self.get_ticker(stock)
        else:
            raise ValueError('Must provide a stock symbol or a stock id')

        params = {'type': interval, 'count': count, 'extendTrading': extendTrading, 'timestamp': timeStamp}
        df = DataFrame(columns=['open', 'high', 'low', 'close', 'volume', 'vwap'])
        df.index.name = 'timestamp'
        response = requests.get(endpoints.bars_crypto(tId), params=params, headers=headers, timeout=self.timeout)
        result = response.json()
        time_zone = timezone(result[0]['timeZone'])
        for row in result[0]['data']:
            row = row.split(',')
            row = ['0' if value == 'null' else value for value in row]
            data = {
                'open': float(row[1]),
                'high': float(row[3]),
                'low': float(row[4]),
                'close': float(row[2]),
                'volume': float(row[6]),
                'vwap': float(row[7])
            }
            #convert to a panda datetime64 which has extra features like floor and resample
            df.loc[to_datetime(datetime.fromtimestamp(int(row[0])).astimezone(time_zone))] = data
        return df.iloc[::-1]

    def get_options_bars(self, derivativeId=None, interval='1m', count=1, direction=1, timeStamp=None):
        '''
        get bars returns a pandas dataframe
        params:
            derivativeId: to be obtained from option chain, eg option_chain[0]['call']['tickerId']
            interval: 1m, 5m, 30m, 60m, 1d
            count: number of bars to return
            direction: 1 ignores {count} parameter & returns all bars on and after timestamp
                       setting any other value will ignore timestamp & return latest {count} bars
            timeStamp: If epoc timestamp is provided, return bar count up to timestamp. If not set default to current time.
        '''
        headers = self.build_req_headers()
        if derivativeId is None:
            raise ValueError('Must provide a derivative ID')

        params = {'type': interval, 'count': count, 'direction': direction, 'timestamp': timeStamp}
        df = DataFrame(columns=['open', 'high', 'low', 'close', 'volume', 'vwap'])
        df.index.name = 'timestamp'
        response = requests.get(endpoints.options_bars(derivativeId), params=params, headers=headers, timeout=self.timeout)
        result = response.json()
        time_zone = timezone(result[0]['timeZone'])
        for row in result[0]['data'] :
            row = row.split(',')
            row = ['0' if value == 'null' else value for value in row]
            data = {
                'open': float(row[1]),
                'high': float(row[3]),
                'low': float(row[4]),
                'close': float(row[2]),
                'volume': float(row[6]),
                'vwap': float(row[7])
            }
            #convert to a panda datetime64 which has extra features like floor and resample
            df.loc[to_datetime(datetime.fromtimestamp(int(row[0])).astimezone(time_zone))] = data
        return df.iloc[::-1]

    def get_calendar(self,stock=None, tId=None):
        '''
        There doesn't seem to be a way to get the times the market is open outside of the charts.
        So, best way to tell if the market is open is to pass in a popular stock like AAPL then
        and see the open and close hours as would be marked on the chart
        and see if the last trade date is the same day as today's date
        :param stock:
        :param tId:
        :return: dict of 'market open', 'market close', 'last trade date'
        '''
        headers = self.build_req_headers()
        if not tId is None:
            pass
        elif not stock is None:
            tId = self.get_ticker(stock)
        else:
            raise ValueError('Must provide a stock symbol or a stock id')

        params = {'type': 'm1', 'count': 1, 'extendTrading': 0}
        response = requests.get(endpoints.bars(tId), params=params, headers=headers, timeout=self.timeout)
        result = response.json()
        time_zone = timezone(result[0]['timeZone'])
        last_trade_date = datetime.fromtimestamp(int(result[0]['data'][0].split(',')[0])).astimezone(time_zone)
        today = datetime.today().astimezone()  #use no time zone to have it pull in local time zone

        if last_trade_date.date() < today.date():
            # don't know what today's open and close times are, since no trade for today yet
            return {'market open': None, 'market close': None, 'trading day': False}

        for d in result[0]['dates']:
            if d['type'] == 'T':
                market_open = today.replace(
                    hour=int(d['start'].split(':')[0]),
                    minute=int(d['start'].split(':')[1]),
                    second=0)
                market_open -= timedelta(microseconds=market_open.microsecond)
                market_open = market_open.astimezone(time_zone)  #set to market timezone

                market_close = today.replace(
                    hour=int(d['end'].split(':')[0]),
                    minute=int(d['end'].split(':')[1]),
                    second=0)
                market_close -= timedelta(microseconds=market_close.microsecond)
                market_close = market_close.astimezone(time_zone) #set to market timezone

                #this implies that we have waited a few minutes from the open before trading
                return {'market open': market_open ,  'market close':market_close, 'trading day':True}
        #otherwise
        return None

    def get_dividends(self):
        ''' Return account's incoming dividend info '''
        headers = self.build_req_headers()
        data = {}
        response = requests.post(endpoints.dividends(self._account_id), json=data, headers=headers, timeout=self.timeout)
        return response.json()

    def get_five_min_ranking(self, extendTrading=0):
        '''
        get 5 minute trend ranking
        '''
        rank = []
        headers = self.build_req_headers()
        params = {'regionId': self._region_code, 'userRegionId': self._region_code, 'platform': 'pc', 'limitCards': 'latestActivityPc'}
        response = requests.get(endpoints.rankings(), params=params, headers=headers, timeout=self.timeout)
        result = response.json()[0].get('data')
        if extendTrading:
            for data in result:
                if data['id'] == 'latestActivityPc.faList':
                    rank = data['data']
        else:
            for data in result:
                if data['id'] == 'latestActivityPc.5minutes':
                    rank = data['data']
        return rank

    def get_watchlists(self, as_list_symbols=False) :
        """
        get user watchlists
        """
        headers = self.build_req_headers()
        params = {'version': 0}
        response = requests.get(endpoints.portfolio_lists(), params=params, headers=headers, timeout=self.timeout)

        if not as_list_symbols :
            return response.json()['portfolioList']
        else:
            list_ticker = response.json()['portfolioList'][0].get('tickerList')
            return list(map(lambda x: x.get('symbol'), list_ticker))

    def get_account_type(self, username='') :
        try:
            validate_email(username)
            account_type = 2 # email
        except EmailNotValidError as _e:
            account_type = 1 # phone

        return account_type

    def is_logged_in(self):
        '''
        Check if login session is active
        '''
        try:
            self.get_account_id()
        except KeyError:
            return False
        else:
            return True


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Interface with Webull. Paper trading is not the default.')
    parser.add_argument('-p', '--use-paper', help='Use paper account instead.', action='store_true')
    args = parser.parse_args()
