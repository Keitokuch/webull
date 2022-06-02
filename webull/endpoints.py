base_info_url = 'https://infoapi.webull.com/api'
base_options_url = 'https://quoteapi.webullbroker.com/api'
base_options_gw_url = 'https://quotes-gw.webullbroker.com/api'
base_paper_url = 'https://act.webullbroker.com/webull-paper-center/api'
base_quote_url = 'https://quoteapi.webullbroker.com/api'
base_securities_url = 'https://securitiesapi.webullbroker.com/api'
base_trade_url = 'https://tradeapi.webullbroker.com/api/trade'
base_user_url = 'https://userapi.webull.com/api'
base_userbroker_url = 'https://userapi.webullbroker.com/api'
base_ustrade_url = 'https://ustrade.webullfinance.com/api'
base_paperfintech_url = 'https://act.webullfintech.com/webull-paper-center/api'
base_fintech_gw_url = 'https://quotes-gw.webullfintech.com/api'
base_userfintech_url = 'https://userapi.webullfintech.com/api'
base_new_trade_url = 'https://trade.webullfintech.com/api'
base_ustradebroker_url = 'https://ustrade.webullbroker.com/api'

def account(account_id):
    return f'{base_trade_url}/v3/home/{account_id}'

def account_id():
    return f'{base_trade_url}/account/getSecAccountList/v5'

def account_activities(account_id):
    return f'{base_ustrade_url}/trade/v2/funds/{account_id}/activities'

def active_gainers_losers(direction, region_code, rank_type, num) :
      if direction == 'gainer' :
          url = 'topGainers'
      elif direction == 'loser' :
          url = 'dropGainers'
      else :
          url = 'topActive'
      return f'{base_fintech_gw_url}/wlas/ranking/{url}?regionId={region_code}&rankType={rank_type}&pageIndex=1&pageSize={num}'

def add_alert():
    return f'{base_userbroker_url}/user/warning/v2/manage/overlap'

def analysis(stock):
    return f'{base_securities_url}/securities/ticker/v5/analysis/{stock}'

def analysis_shortinterest(stock):
    return f'{base_securities_url}/securities/stock/{stock}/shortInterest'

def analysis_institutional_holding(stock):
    return f'{base_securities_url}/securities/stock/v5/{stock}/institutionalHolding'

def analysis_etf_holding(stock, has_num, page_size):
    return f'{base_securities_url}/securities/stock/v5/{stock}/belongEtf?hasNum={has_num}&pageSize={page_size}'

def analysis_capital_flow(stock, show_hist):
    return f'{base_securities_url}/wlas/capitalflow/ticker?tickerId={stock}&showHis={show_hist}'

def bars(stock):
    return f'{base_quote_url}/quote/tickerChartDatas/v5/{stock}'

def bars_crypto(stock):
    return f'{base_fintech_gw_url}/crypto/charts/query?tickerIds={stock}'

def cancel_order(account_id):
    return f'{base_ustrade_url}/trade/order/{account_id}/cancelStockOrder/'

def modify_otoco_orders(account_id):
    return f'{base_ustrade_url}/trade/v2/corder/stock/modify/{account_id}'

def cancel_otoco_orders(account_id, combo_id):
    return f'{base_ustrade_url}/trade/v2/corder/stock/cancel/{account_id}/{combo_id}'

def check_otoco_orders(account_id):
    return f'{base_ustrade_url}/trade/v2/corder/stock/check/{account_id}'

def place_otoco_orders(account_id):
    return f'{base_ustrade_url}/trade/v2/corder/stock/place/{account_id}'

def dividends(account_id):
    return f'{base_trade_url}/v2/account/{account_id}/dividends?direct=in'

def fundamentals(stock):
    return f'{base_securities_url}/securities/financial/index/{stock}'

def is_tradable(stock):
    return f'{base_trade_url}/ticker/broker/permissionV2?tickerId={stock}'

def list_alerts():
    return f'{base_userbroker_url}/user/warning/v2/query/tickers'

def login():
    return f'{base_user_url}/passport/login/v5/account'

def get_mfa() :
    return f'{base_userfintech_url}/passport/v2/verificationCode/send'

def check_mfa() :
    return f'{base_userfintech_url}/passport/v2/verificationCode/checkCode'

def get_security(username, account_type, region_code, event, time, url=0) :
    if url == 1 :
        url = 'getPrivacyQuestion'
    else :
        url = 'getSecurityQuestion'

    return f'{base_userfintech_url}/user/risk/{url}?account={username}&accountType={account_type}&regionId={region_code}&event={event}&v={time}'

def next_security(username, account_type, region_code, event, time, url=0) :
    if url == 1 :
        url = 'nextPrivacyQuestion'
    else :
        url = 'nextSecurityQuestion'

    return f'{base_userfintech_url}/user/risk/{url}?account={username}&accountType={account_type}&regionId={region_code}&event={event}&v={time}'

def check_security() :
    return f'{base_userfintech_url}/user/risk/checkAnswer'

def logout():
    return f'{base_userbroker_url}/passport/login/logout'

def news(stock, Id, items):
    return f'{base_fintech_gw_url}/information/news/tickerNews?tickerId={stock}&currentNewsId={Id}&pageSize={items}'

def option_quotes():
    return f'{base_options_gw_url}/quote/option/query/list'

def options(stock):
    return f'{base_options_url}/quote/option/{stock}/list'

def options_exp_date(stock):
    return f'{base_options_url}/quote/option/{stock}/list'

def options_bars(derivativeId):
    return f'{base_options_gw_url}/quote/option/chart/query?derivativeId={derivativeId}'

def orders(account_id, page_size):
    return f'{base_ustradebroker_url}/trade/v2/option/list?secAccountId={account_id}&startTime=1970-0-1&dateType=ORDER&pageSize={page_size}&status='

def history(account_id):
    return f'{base_ustrade_url}/trading/v1/webull/order/list?secAccountId={account_id}'

def paper_orders(paper_account_id, page_size):
    return f'{base_paper_url}/paper/1/acc/{paper_account_id}/order?&startTime=1970-0-1&dateType=ORDER&pageSize={page_size}&status='

def paper_account(paper_account_id):
    return f'{base_paperfintech_url}/paper/1/acc/{paper_account_id}'

def paper_account_id():
    return f'{base_paperfintech_url}/myaccounts/true'

def paper_cancel_order(paper_account_id, order_id):
    return f'{base_paper_url}/paper/1/acc/{paper_account_id}/orderop/cancel/{order_id}'

def paper_modify_order(paper_account_id, order_id):
    return f'{base_paper_url}/paper/1/acc/{paper_account_id}/orderop/modify/{order_id}'

def paper_place_order(paper_account_id, stock):
    return f'{base_paper_url}/paper/1/acc/{paper_account_id}/orderop/place/{stock}'

def place_option_orders(account_id):
    return f'{base_ustrade_url}/trade/v2/option/placeOrder/{account_id}'

def place_orders(account_id):
    return f'{base_ustrade_url}/trade/order/{account_id}/placeStockOrder'

def modify_order(account_id, order_id):
    return f'{base_ustrade_url}/trading/v1/webull/order/stockOrderModify?secAccountId={account_id}'

def quotes(stock):
    return f'{base_options_gw_url}/quotes/ticker/getTickerRealTime?tickerId={stock}&includeSecu=1&includeQuote=1'

def rankings():
    return f'{base_securities_url}/securities/market/v5/6/portal'

def refresh_login():
    return f'{base_user_url}/passport/refreshToken?refreshToken='

def remove_alert():
    return f'{base_userbroker_url}/user/warning/v2/manage/overlap'

def replace_option_orders(account_id):
    return f'{base_trade_url}/v2/option/replaceOrder/{account_id}'

def stock_id(stock, region_code):
    return f'{base_options_gw_url}/search/pc/tickers?keyword={stock}&pageIndex=1&pageSize=20&regionId={region_code}'

def trade_token():
    return f'{base_new_trade_url}/trading/v1/global/trade/login'

def user():
    return f'{base_user_url}/user'

def screener():
    return f'{base_userbroker_url}/wlas/screener/ng/query'

def social_posts(topic, num=100):
    return f'{base_user_url}/social/feed/topic/{topic}/posts?size={num}'

def social_home(topic, num=100):
    return f'{base_user_url}/social/feed/topic/{topic}/home?size={num}'

def portfolio_lists():
    return f'{base_options_gw_url}/personal/portfolio/v2/check'
