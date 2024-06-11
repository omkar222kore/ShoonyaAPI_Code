import time
import schedule
import logging
from threading import Timer
import pandas as pd
import concurrent.futures
import pyotp
from NorenRestApiPy.NorenApi import NorenApi
import requests
from bs4 import BeautifulSoup
import json
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
from apscheduler.schedulers.background import BackgroundScheduler



class ShoonyaApiPy(NorenApi):
    def __init__(self):
        NorenApi.__init__(self, host='https://api.shoonya.com/NorenWClientTP/', websocket='wss://api.shoonya.com/NorenWSTP/')
        global api
        api = self
        # Enable debug to see request and responses
        logging.basicConfig(level=logging.DEBUG)

# Start of our program
api = ShoonyaApiPy()

# Credentials
user = 'FA74468'
pwd = 'GURU222kore$'
token = 'XT2L66VT73Q22P33BNCHKN6WA2Q37KK6'
factor2 = pyotp.TOTP(token).now()
vc = 'FA74468_U'
app_key = 'c98e82a190da8181c80fb94cf0a31144'
imei = 'abc1234'

# Make the opt call

ret = api.login(userid=user, password=pwd, twoFA=factor2, vendor_code=vc, api_secret=app_key, imei=imei)
print(ret)
pd.DataFrame([ret])


Stock_Symbols=['ZYDUSLIFE', 'ZOMATO', 'ZFCVINDIA', 'ZENSARTECH', 'ZEEL', 'YESBANK', 'WIPRO', 'WHIRLPOOL', 'WESTLIFE', 'WELSPUNLIV', 'WELCORP', 'VTL', 'VOLTAS', 'VIPIND', 'VIJAYA', 'VGUARD', 'VEDL', 'VBL', 'VARROC', 'VAIBHAVGBL', 'UTIAMC', 'USHAMART', 'UPL', 'UNOMINDA', 'UNIONBANK', 'ULTRACEMCO', 'UJJIVANSFB', 'UCOBANK', 'UBL', 'TVSSCS', 'TVSMOTOR', 
                'TV18BRDCST', 'TTML', 'TRIVENI', 'TRITURBINE', 'TRIDENT', 'TRENT', 'TORNTPOWER', 'TORNTPHARM', 'TMB', 'TITAN', 'TITAGARH', 'TIMKEN', 'TIINDIA', 'THERMAX', 'TEJASNET', 'TECHM', 'TCS', 'TATATECH', 'TATASTEEL', 'TATAPOWER', 'TATAMTRDVR', 'TATAMOTORS', 'TATAELXSI', 'TATACONSUM', 'TATACOMM', 'TATACHEM', 'TANLA', 'SYRMA', 'SYNGENE', 'SWSOLAR', 
                'SWANENERGY', 'SUVENPHAR', 'SUPREMEIND', 'SUNTV', 'SUNTECK', 'SUNPHARMA', 'SUNDRMFAST', 'SUNDARMFIN', 'SUMICHEM', 'STLTECH', 'STARHEALTH', 'SRF', 'SPARC', 'SONATSOFTW', 'SONACOMS', 'SOLARINDS', 'SOBHA', 'SKFINDIA', 'SJVN', 'SIGNATURE', 'SIEMENS', 'SHYAMMETL', 'SHRIRAMFIN', 'SHREECEM', 'SCHAEFFLER', 'SBIN', 'SBILIFE', 'SBICARD', 'SBFC', 'SAREGAMA', 
                'SAPPHIRE', 'SANOFI', 'SAIL', 'SAFARI', 'RVNL', 'RTNINDIA', 'RRKABEL', 'ROUTE', 'RKFORGE', 'RITES', 'RHIM', 'RENUKA', 'RELIANCE', 'REDINGTON', 'RECLTD', 'RCF', 'RBLBANK', 'RBA', 'RAYMOND', 'RATNAMANI', 'RAMCOCEM', 'RAJESHEXPO', 'RAINBOW', 'RAILTEL', 'RADICO', 'QUESS', 'PVRINOX', 'PRSMJOHNSN', 'PRINCEPIPE', 'PRESTIGE', 'PRAJIND', 'PPLPHARMA', 'POWERINDIA', 
                'POWERGRID', 'POONAWALLA', 'POLYMED', 'POLYCAB', 'POLICYBZR', 'PNCINFRA', 'PNBHOUSING', 'PNB', 'PIIND', 'PIDILITIND', 'PHOENIXLTD', 'PGHH', 'PFC', 'PETRONET', 'PERSISTENT', 'PEL', 'PCBL', 'PAYTM', 'PATANJALI', 'PAGEIND', 'ONGC', 'OLECTRA', 'OIL', 'OFSS', 'OBEROIRLTY', 'NYKAA', 'NUVOCO', 'NUVAMA', 'NTPC', 'NSLNISP', 'NMDC', 'NLCINDIA', 'NIACL', 'NHPC', 'NH', 'NETWORK18', 
                'NESTLEIND', 'NCC', 'NBCC', 'NAVINFLUOR', 'NAUKRI', 'NATIONALUM', 'NATCOPHARM', 'NAM-INDIA', 'MUTHOOTFIN', 'MTARTECH', 'MSUMI', 'MRPL', 'MRF', 'MPHASIS', 'MOTILALOFS', 'MOTHERSON', 'MMTC', 'MINDACORP', 'MHRIL', 'MGL', 'MFSL', 'METROPOLIS', 'METROBRAND', 'MEDPLUS', 'MEDANTA', 'MCX', 'MCDOWELL-N', 'MAZDOCK', 'MAXHEALTH', 'MASTEK', 'MARUTI', 'MARICO', 'MAPMYINDIA', 'MANYAVAR', 
                'MANKIND', 'MANAPPURAM', 'MAHSEAMLES', 'MAHLIFE', 'MAHABANK', 'M&MFIN', 'M&M', 'LXCHEM', 'LUPIN', 'LTTS', 'LTIM', 'LTF', 'LT', 'LODHA', 'LLOYDSME', 'LINDEINDIA', 'LICI', 'LICHSGFIN', 'LEMONTREE', 'LAURUSLABS', 'LALPATHLAB', 'KSB', 'KRBL', 'KPRMILL', 'KPITTECH', 'KPIL', 'KOTAKBANK', 'KNRCON', 'KIMS', 'KFINTECH', 'KEI', 'KEC', 'KAYNES', 'KARURVYSYA', 'KANSAINER', 'KALYANKJIL', 
                'KAJARIACER', 'JYOTHYLAB', 'JWL', 'JUSTDIAL', 'JUBLPHARMA', 'JUBLINGREA', 'JUBLFOOD', 'JSWSTEEL', 'JSWINFRA', 'JSWENERGY', 'JSL', 'JMFINANCIL', 'JKPAPER', 'JKLAKSHMI', 'JKCEMENT', 'JIOFIN', 'JINDALSTEL', 'JINDALSAW', 'JBMA', 'JBCHEPHARM', 'J&KBANK', 'ITI', 'ITC', 'ISEC', 'IRFC', 'IRCTC', 'IRCON', 'IRB', 'IPCALAB', 'IOC', 'IOB', 'INTELLECT', 'INOXWIND', 'INFY', 'INDUSTOWER', 
                'INDUSINDBK', 'INDIGOPNTS', 'INDIGO', 'INDIANB', 'INDIAMART', 'INDIACEM', 'INDHOTEL', 'IIFL', 'IGL', 'IEX', 'IDFCFIRSTB', 'IDFC', 'IDEA', 'IDBI', 'ICICIPRULI', 'ICICIGI', 'ICICIBANK', 'IBULHSGFIN', 'HUDCO', 'HONAUT', 'HONASA', 'HOMEFIRST', 'HINDZINC', 'HINDUNILVR', 'HINDPETRO', 'HINDCOPPER', 'HINDALCO', 'HFCL', 'HEROMOTOCO', 'HEG', 'HDFCLIFE', 'HDFCBANK', 'HDFCAMC', 'HCLTECH', 'HBLPOWER', 'HAVELLS', 'HAPPYFORGE',
                'HAPPSTMNDS', 'HAL', 'GUJGASLTD', 'GSPL', 'GSFC', 'GRSE', 'GRINDWELL', 'GRASIM', 'GRAPHITE', 'GRANULES', 'GPPL', 'GPIL', 'GODREJPROP', 'GODREJIND', 'GODREJCP', 'GODFRYPHLP', 'GNFC', 'GMRINFRA', 'GMMPFAUDLR', 'GMDCLTD', 'GLS', 'GLENMARK', 'GLAXO', 'GLAND', 'GILLETTE', 'GICRE', 'GESHIP', 'GAIL', 'GAEL', 'FSL', 'FORTIS', 'FLUOROCHEM', 'FIVESTAR', 'FINPIPE', 'FINEORG', 'FINCABLES', 'FEDERALBNK', 'FDC', 'FACT', 'EXIDEIND',
                'ESCORTS', 'ERIS', 'EQUITASBNK', 'EPL', 'ENGINERSIN', 'ENDURANCE', 'EMAMILTD', 'ELGIEQUIP', 'ELECON', 'EIHOTEL', 'EIDPARRY', 'EICHERMOT', 'ECLERX', 'EASEMYTRIP', 'DRREDDY', 'DOMS', 'DMART', 'DLF', 'DIXON', 'DIVISLAB', 'DEVYANI', 'DELHIVERY', 'DEEPAKNTR', 'DEEPAKFERT', 'DCMSHRIRAM', 'DATAPATTNS', 'DALBHARAT', 'DABUR', 'CYIENT', 'CUMMINSIND', 'CUB', 'CSBBANK', 'CROMPTON', 'CRISIL',
                'CREDITACC', 'CRAFTSMAN', 'COROMANDEL', 'CONCORDBIO', 'CONCOR', 'COLPAL', 'COFORGE', 'COCHINSHIP', 'COALINDIA', 'CLEAN', 'CIPLA', 'CIEINDIA', 'CHOLAHLDNG', 'CHOLAFIN', 'CHENNPETRO', 'CHEMPLASTS', 'CHAMBLFERT', 'CHALET', 'CGPOWER', 'CGCL', 'CESC', 'CERA', 'CENTURYTEX', 'CENTURYPLY', 'CENTRALBK', 'CELLO', 'CEATLTD', 'CDSL', 'CCL', 'CASTROLIND', 'CARBORUNIV', 'CAPLIPOINT', 'CANFINHOME', 'CANBK', 'CAMS', 'CAMPUS',
                'BSOFT', 'BSE', 'BRITANNIA', 'BRIGADE', 'BPCL', 'BOSCHLTD', 'BORORENEW', 'BLUESTARCO', 'BLUEDART', 'BLS', 'BIRLACORPN', 'BIOCON', 'BIKAJI', 'BHEL', 'BHARTIARTL', 'BHARATFORG', 'BERGEPAINT', 'BEML', 'BEL', 'BDL', 'BBTC', 'BAYERCROP', 'BATAINDIA', 'BANKINDIA', 'BANKBARODA', 'BANDHANBNK', 'BALRAMCHIN', 'BALKRISIND', 'BALAMINES', 'BAJFINANCE', 'BAJAJHLDNG', 'BAJAJFINSV', 'BAJAJ-AUTO', 'AXISBANK', 'AWL', 'AVANTIFEED', 
                'AUROPHARMA', 'AUBANK', 'ATUL', 'ATGL', 'ASTRAZEN', 'ASTRAL', 'ASTERDM', 'ASIANPAINT', 'ASHOKLEY', 'ASAHIINDIA', 'ARE&M', 'APTUS', 'APOLLOTYRE', 'APOLLOHOSP', 'APLLTD', 'APLAPOLLO', 'APARINDS', 'ANURAS', 'ANGELONE', 'ANANDRATHI', 'AMBUJACEM', 'AMBER', 'ALOKINDS', 'ALLCARGO', 'ALKYLAMINE', 'ALKEM', 'AJANTPHARM', 'AIAENG', 'AFFLE', 'AETHER', 'AEGISCHEM', 'ADANIPOWER', 'ADANIPORTS', 'ADANIGREEN', 'ADANIENT', 'ADANIENSOL', 
                'ACI', 'ACE', 'ACC', 'ABFRL', 'ABCAPITAL', 'ABBOTINDIA', 'ABB', 'AAVAS', 'AARTIIND', '3MINDIA', '360ONE']


Stock_Tokens=['ZYDUSLIFE-EQ', 'ZOMATO-EQ', 'ZFCVINDIA-EQ', 'ZENSARTECH-EQ', 'ZEEL-EQ', 'YESBANK-EQ', 'WIPRO-EQ', 'WHIRLPOOL-EQ',
              'WESTLIFE-EQ', 'WELSPUNLIV-EQ', 'WELCORP-EQ', 'VTL-EQ', 'VOLTAS-EQ', 'VIPIND-EQ', 'VIJAYA-EQ', 'VGUARD-EQ', 'VEDL-EQ', 
              'VBL-EQ', 'VARROC-EQ', 'VAIBHAVGBL-EQ', 'UTIAMC-EQ', 'USHAMART-EQ', 'UPL-EQ', 'UNOMINDA-EQ', 'UNIONBANK-EQ', 'ULTRACEMCO-EQ',
              'UJJIVANSFB-EQ', 'UCOBANK-EQ', 'UBL-EQ', 'TVSSCS-EQ', 'TVSMOTOR-EQ', 'TV18BRDCST-EQ', 'TTML-EQ', 'TRIVENI-EQ', 'TRITURBINE-EQ', 
              'TRIDENT-EQ', 'TRENT-EQ', 'TORNTPOWER-EQ', 'TORNTPHARM-EQ', 'TMB-EQ', 'TITAN-EQ', 'TITAGARH-EQ', 'TIMKEN-EQ', 'TIINDIA-EQ',
              'THERMAX-EQ', 'TEJASNET-EQ', 'TECHM-EQ', 'TCS-EQ', 'TATATECH-EQ', 'TATASTEEL-EQ', 'TATAPOWER-EQ', 'TATAMTRDVR-EQ', 'TATAMOTORS-EQ', 
              'TATAELXSI-EQ', 'TATACONSUM-EQ', 'TATACOMM-EQ', 'TATACHEM-EQ', 'TANLA-EQ', 'SYRMA-EQ', 'SYNGENE-EQ', 'SWSOLAR-EQ', 'SWANENERGY-EQ', 
              'SUVENPHAR-EQ', 'SUPREMEIND-EQ', 'SUNTV-EQ', 'SUNTECK-EQ', 'SUNPHARMA-EQ', 'SUNDRMFAST-EQ', 'SUNDARMFIN-EQ', 'SUMICHEM-EQ', 
              'STLTECH-EQ', 'STARHEALTH-EQ', 'SRF-EQ', 'SPARC-EQ', 'SONATSOFTW-EQ', 'SONACOMS-EQ', 'SOLARINDS-EQ', 'SOBHA-EQ', 'SKFINDIA-EQ', 
              'SJVN-EQ', 'SIGNATURE-EQ', 'SIEMENS-EQ', 'SHYAMMETL-EQ', 'SHRIRAMFIN-EQ', 'SHREECEM-EQ', 'SCHAEFFLER-EQ', 'SBIN-EQ', 'SBILIFE-EQ', 
              'SBICARD-EQ', 'SBFC-EQ', 'SAREGAMA-EQ', 'SAPPHIRE-EQ', 'SANOFI-EQ', 'SAIL-EQ', 'SAFARI-EQ', 'RVNL-EQ', 'RTNINDIA-EQ', 'RRKABEL-EQ',
              'ROUTE-EQ', 'RKFORGE-EQ', 'RITES-EQ', 'RHIM-EQ', 'RENUKA-EQ', 'RELIANCE-EQ', 'REDINGTON-EQ', 'RECLTD-EQ', 'RCF-EQ', 'RBLBANK-EQ', 
              'RBA-EQ', 'RAYMOND-EQ', 'RATNAMANI-EQ', 'RAMCOCEM-EQ', 'RAJESHEXPO-EQ', 'RAINBOW-EQ', 'RAILTEL-EQ', 'RADICO-EQ', 'QUESS-EQ', 
              'PVRINOX-EQ', 'PRSMJOHNSN-EQ', 'PRINCEPIPE-EQ', 'PRESTIGE-EQ', 'PRAJIND-EQ', 'PPLPHARMA-EQ', 'POWERINDIA-EQ', 'POWERGRID-EQ', 
              'POONAWALLA-EQ', 'POLYMED-EQ', 'POLYCAB-EQ', 'POLICYBZR-EQ', 'PNCINFRA-EQ', 'PNBHOUSING-EQ', 'PNB-EQ', 'PIIND-EQ', 'PIDILITIND-EQ',
              'PHOENIXLTD-EQ', 'PGHH-EQ', 'PFC-EQ', 'PETRONET-EQ', 'PERSISTENT-EQ', 'PEL-EQ', 'PCBL-EQ', 'PAYTM-EQ', 'PATANJALI-EQ', 'PAGEIND-EQ',
              'ONGC-EQ', 'OLECTRA-EQ', 'OIL-EQ', 'OFSS-EQ', 'OBEROIRLTY-EQ', 'NYKAA-EQ', 'NUVOCO-EQ', 'NUVAMA-EQ', 'NTPC-EQ', 'NSLNISP-EQ', 'NMDC-EQ',
              'NLCINDIA-EQ', 'NIACL-EQ', 'NHPC-EQ', 'NH-EQ', 'NETWORK18-EQ', 'NESTLEIND-EQ', 'NCC-EQ', 'NBCC-EQ', 'NAVINFLUOR-EQ', 'NAUKRI-EQ', 
              'NATIONALUM-EQ', 'NATCOPHARM-EQ', 'NAM-INDIA-EQ', 'MUTHOOTFIN-EQ', 'MTARTECH-EQ', 'MSUMI-EQ', 'MRPL-EQ', 'MRF-EQ', 'MPHASIS-EQ', 
              'MOTILALOFS-EQ', 'MOTHERSON-EQ', 'MMTC-EQ', 'MINDACORP-EQ', 'MHRIL-EQ', 'MGL-EQ', 'MFSL-EQ', 'METROPOLIS-EQ', 'METROBRAND-EQ', 
              'MEDPLUS-EQ', 'MEDANTA-EQ', 'MCX-EQ', 'MCDOWELL-N-EQ', 'MAZDOCK-EQ', 'MAXHEALTH-EQ', 'MASTEK-EQ', 'MARUTI-EQ', 'MARICO-EQ', 
              'MAPMYINDIA-EQ', 'MANYAVAR-EQ', 'MANKIND-EQ', 'MANAPPURAM-EQ', 'MAHSEAMLES-EQ', 'MAHLIFE-EQ', 'MAHABANK-EQ', 'M&MFIN-EQ', 'M&M-EQ', 
              'LXCHEM-EQ', 'LUPIN-EQ', 'LTTS-EQ', 'LTIM-EQ', 'LTF-EQ', 'LT-EQ', 'LODHA-EQ', 'LLOYDSME-EQ', 'LINDEINDIA-EQ', 'LICI-EQ', 'LICHSGFIN-EQ', 
              'LEMONTREE-EQ', 'LAURUSLABS-EQ', 'LALPATHLAB-EQ', 'KSB-EQ', 'KRBL-EQ', 'KPRMILL-EQ', 'KPITTECH-EQ', 'KPIL-EQ', 'KOTAKBANK-EQ', 
              'KNRCON-EQ', 'KIMS-EQ', 'KFINTECH-EQ', 'KEI-EQ', 'KEC-EQ', 'KAYNES-EQ', 'KARURVYSYA-EQ', 'KANSAINER-EQ', 'KALYANKJIL-EQ', 
              'KAJARIACER-EQ', 'JYOTHYLAB-EQ', 'JWL-EQ', 'JUSTDIAL-EQ', 'JUBLPHARMA-EQ', 'JUBLINGREA-EQ', 'JUBLFOOD-EQ', 'JSWSTEEL-EQ', 
              'JSWINFRA-EQ', 'JSWENERGY-EQ', 'JSL-EQ', 'JMFINANCIL-EQ', 'JKPAPER-EQ', 'JKLAKSHMI-EQ', 'JKCEMENT-EQ', 'JIOFIN-EQ', 
              'JINDALSTEL-EQ', 'JINDALSAW-EQ', 'JBMA-EQ', 'JBCHEPHARM-EQ', 'J&KBANK-EQ', 'ITI-EQ', 'ITC-EQ', 'ISEC-EQ', 'IRFC-EQ', 
              'IRCTC-EQ', 'IRCON-EQ', 'IRB-EQ', 'IPCALAB-EQ', 'IOC-EQ', 'IOB-EQ', 'INTELLECT-EQ', 'INOXWIND-EQ', 'INFY-EQ', 'INDUSTOWER-EQ', 
              'INDUSINDBK-EQ', 'INDIGOPNTS-EQ', 'INDIGO-EQ', 'INDIANB-EQ', 'INDIAMART-EQ', 'INDIACEM-EQ', 'INDHOTEL-EQ', 'IIFL-EQ', 'IGL-EQ', 
              'IEX-EQ', 'IDFCFIRSTB-EQ', 'IDFC-EQ', 'IDEA-EQ', 'IDBI-EQ', 'ICICIPRULI-EQ', 'ICICIGI-EQ', 'ICICIBANK-EQ', 'IBULHSGFIN-EQ', 
              'HUDCO-EQ', 'HONAUT-EQ', 'HONASA-EQ', 'HOMEFIRST-EQ', 'HINDZINC-EQ', 'HINDUNILVR-EQ', 'HINDPETRO-EQ', 'HINDCOPPER-EQ', 
              'HINDALCO-EQ', 'HFCL-EQ', 'HEROMOTOCO-EQ', 'HEG-EQ', 'HDFCLIFE-EQ', 'HDFCBANK-EQ', 'HDFCAMC-EQ', 'HCLTECH-EQ', 'HBLPOWER-EQ',
              'HAVELLS-EQ', 'HAPPYFORGE-EQ', 'HAPPSTMNDS-EQ', 'HAL-EQ', 'GUJGASLTD-EQ', 'GSPL-EQ', 'GSFC-EQ', 'GRSE-EQ', 'GRINDWELL-EQ', 
              'GRASIM-EQ', 'GRAPHITE-EQ', 'GRANULES-EQ', 'GPPL-EQ', 'GPIL-EQ', 'GODREJPROP-EQ', 'GODREJIND-EQ', 'GODREJCP-EQ', 'GODFRYPHLP-EQ',
              'GNFC-EQ', 'GMRINFRA-EQ', 'GMMPFAUDLR-EQ', 'GMDCLTD-EQ', 'GLS-EQ', 'GLENMARK-EQ', 'GLAXO-EQ', 'GLAND-EQ', 'GILLETTE-EQ', 'GICRE-EQ', 
              'GESHIP-EQ', 'GAIL-EQ', 'GAEL-EQ', 'FSL-EQ', 'FORTIS-EQ', 'FLUOROCHEM-EQ', 'FIVESTAR-EQ', 'FINPIPE-EQ', 'FINEORG-EQ', 'FINCABLES-EQ', 
              'FEDERALBNK-EQ', 'FDC-EQ', 'FACT-EQ', 'EXIDEIND-EQ', 'ESCORTS-EQ', 'ERIS-EQ', 'EQUITASBNK-EQ', 'EPL-EQ', 'ENGINERSIN-EQ', 
              'ENDURANCE-EQ', 'EMAMILTD-EQ', 'ELGIEQUIP-EQ', 'ELECON-EQ', 'EIHOTEL-EQ', 'EIDPARRY-EQ', 'EICHERMOT-EQ', 'ECLERX-EQ', 'EASEMYTRIP-EQ', 
              'DRREDDY-EQ', 'DOMS-EQ', 'DMART-EQ', 'DLF-EQ', 'DIXON-EQ', 'DIVISLAB-EQ', 'DEVYANI-EQ', 'DELHIVERY-EQ', 'DEEPAKNTR-EQ', 'DEEPAKFERT-EQ',
              'DCMSHRIRAM-EQ', 'DATAPATTNS-EQ', 'DALBHARAT-EQ', 'DABUR-EQ', 'CYIENT-EQ', 'CUMMINSIND-EQ', 'CUB-EQ', 'CSBBANK-EQ', 'CROMPTON-EQ', 
              'CRISIL-EQ', 'CREDITACC-EQ', 'CRAFTSMAN-EQ', 'COROMANDEL-EQ', 'CONCORDBIO-EQ', 'CONCOR-EQ', 'COLPAL-EQ', 'COFORGE-EQ', 'COCHINSHIP-EQ', 
              'COALINDIA-EQ', 'CLEAN-EQ', 'CIPLA-EQ', 'CIEINDIA-EQ', 'CHOLAHLDNG-EQ', 'CHOLAFIN-EQ', 'CHENNPETRO-EQ', 'CHEMPLASTS-EQ', 
              'CHAMBLFERT-EQ', 'CHALET-EQ', 'CGPOWER-EQ', 'CGCL-EQ', 'CESC-EQ', 'CERA-EQ', 'CENTURYTEX-EQ', 'CENTURYPLY-EQ', 'CENTRALBK-EQ', 
              'CELLO-EQ', 'CEATLTD-EQ', 'CDSL-EQ', 'CCL-EQ', 'CASTROLIND-EQ', 'CARBORUNIV-EQ', 'CAPLIPOINT-EQ', 'CANFINHOME-EQ', 'CANBK-EQ',
              'CAMS-EQ', 'CAMPUS-EQ', 'BSOFT-EQ', 'BSE-EQ', 'BRITANNIA-EQ', 'BRIGADE-EQ', 'BPCL-EQ', 'BOSCHLTD-EQ', 'BORORENEW-EQ', 'BLUESTARCO-EQ',
              'BLUEDART-EQ', 'BLS-EQ', 'BIRLACORPN-EQ', 'BIOCON-EQ', 'BIKAJI-EQ', 'BHEL-EQ', 'BHARTIARTL-EQ', 'BHARATFORG-EQ', 'BERGEPAINT-EQ', 
              'BEML-EQ', 'BEL-EQ', 'BDL-EQ', 'BBTC-EQ', 'BAYERCROP-EQ', 'BATAINDIA-EQ', 'BANKINDIA-EQ', 'BANKBARODA-EQ', 'BANDHANBNK-EQ', 
              'BALRAMCHIN-EQ', 'BALKRISIND-EQ', 'BALAMINES-EQ', 'BAJFINANCE-EQ', 'BAJAJHLDNG-EQ', 'BAJAJFINSV-EQ', 'BAJAJ-AUTO-EQ', 
              'AXISBANK-EQ', 'AWL-EQ', 'AVANTIFEED-EQ', 'AUROPHARMA-EQ', 'AUBANK-EQ', 'ATUL-EQ', 'ATGL-EQ', 'ASTRAZEN-EQ', 'ASTRAL-EQ',
              'ASTERDM-EQ', 'ASIANPAINT-EQ', 'ASHOKLEY-EQ', 'ASAHIINDIA-EQ', 'ARE&M-EQ', 'APTUS-EQ', 'APOLLOTYRE-EQ', 'APOLLOHOSP-EQ', 
              'APLLTD-EQ', 'APLAPOLLO-EQ', 'APARINDS-EQ', 'ANURAS-EQ', 'ANGELONE-EQ', 'ANANDRATHI-EQ', 'AMBUJACEM-EQ', 'AMBER-EQ', 
              'ALOKINDS-EQ', 'ALLCARGO-EQ', 'ALKYLAMINE-EQ', 'ALKEM-EQ', 'AJANTPHARM-EQ', 'AIAENG-EQ', 'AFFLE-EQ', 'AETHER-EQ', 'AEGISCHEM-EQ', 
              'ADANIPOWER-EQ', 'ADANIPORTS-EQ', 'ADANIGREEN-EQ', 'ADANIENT-EQ', 'ADANIENSOL-EQ', 'ACI-EQ', 'ACE-EQ', 'ACC-EQ', 'ABFRL-EQ', 
              'ABCAPITAL-EQ', 'ABBOTINDIA-EQ', 'ABB-EQ', 'AAVAS-EQ', 'AARTIIND-EQ', '3MINDIA-EQ', '360ONE-EQ']



############################################################################
############################################################################






##################################################################################
##################################################################################
orders_placed = False
stocksList = []  # Define stocksList as global
completed_orders = []  # Track completed orders
all_orders_completed = False
slArray = []
PlaceQtyForEachStockArray = []
remove_stocks = ['M&M-EQ', 'M&MFIN-EQ', 'J&KBANK-EQ']

# Define function to execute the trading strategy
def execute_strategy():
    global slArray, stocksList, orders_placed

    def extract_stock_names(data):
        # Parse the JSON data
        json_data = json.loads(data)

        # Extract stock names from the JSON data
        stocks = json_data.get("stocks", "").split(',')
        stockL = list(stocks)
        print("New stocks List ", stockL)

        return stockL

    # Start a WebDriver (Chrome in this example)
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service)

    url = "https://webhook.site/#!/view/be9a435f-a200-4c08-b2b5-200bd3d63c41/b7885027-c220-4746-abc5-ebe088b20f24/1"
    driver.get(url)

    # Wait for the dynamic content to load
    wait = WebDriverWait(driver, 3)
    element = wait.until(EC.element_to_be_clickable((By.XPATH, '//*[@id="app"]/div/div[1]/div[3]/ul/li[2]/a[1]')))

    # Click on the element to trigger the update
    element.click()

    # Wait for the updated content to load
    updated_element = wait.until(EC.visibility_of_element_located((By.XPATH, '//*[@id="request"]/div[3]/div/div[5]/div/div/div[2]/pre')))

    # Extract the text content of the updated element
    data = updated_element.text.strip()

    # Extract stock names from the data
    stocksList = extract_stock_names(data)

    # Close the browser
    driver.quit()

    # Stock exchange
    exchange = 'NSE'

    # Iterate over each stock symbol
    for i, symbol in enumerate(stocksList):
        try:
            # Remove the specified stocks from the list
            stocksList = [symbol for symbol in stocksList if symbol not in remove_stocks]

            # Find the index of the current symbol in the list of all symbols
            index = Stock_Symbols.index(symbol)

            # Get the token corresponding to the current symbol
            tokenForStock = Stock_Tokens[index]

            # Retrieve quote for the current symbol using the API (replace this with your actual API call)
            quote = api.get_quotes(exchange=exchange, token=tokenForStock)

            # Extract the last traded price (LTP) from the quote
            LTP = float(quote["lp"])

            slArray.append(LTP)

            # Calculate target price and stop loss
            targetPrice = round((LTP * 1.008), 2)
            stopLoss = round((LTP * 0.9955), 2)
            stopLossFinal = round(float(stopLoss) * 10) / 10
            targetPriceFinal = round(float(targetPrice) * 10) / 10

            # Print target price, stop loss, and LTP
            print("Symbol:", symbol)
            print("Stop Loss:", stopLossFinal)
            print("Target Price:", targetPriceFinal)
            print("Last Traded Price (LTP):", LTP)

            # Calculate quantity, capital used, and quantity to place order for each stock
            qtyGet = len(stocksList)
            capUsed = 19600
            capForEachStock = capUsed * 5 / qtyGet

            # To manage no trades on low stocks
            if qtyGet <= 2:
                capForEachStock = 20000
            elif qtyGet == 3:
                capForEachStock = 20000
            else:
                capForEachStock = int(capUsed * 5 / qtyGet)

            PlaceQtyForEachStock = int((capForEachStock / LTP))
            PlaceQtyForEachStockArray.append(PlaceQtyForEachStock)
            print(capForEachStock)

            # Place order using the API (replace this with your actual order placement code)
            api.place_order(buy_or_sell='B', product_type='I', exchange=exchange, tradingsymbol=tokenForStock,
                            quantity=PlaceQtyForEachStock, discloseqty=0, price_type='MKT', trigger_price=None,
                            retention='DAY', remarks='my_order_001', bookprofit_price=targetPriceFinal)

        except ValueError:
            print(f"Symbol {symbol} not found in the list.")
        except Exception as e:
            print(f"Error occurred for symbol {symbol}: {e}")

    # Indicate that orders have been placed
    orders_placed = True




# Function to book orders
def book_orders(scheduler=None):
    global stocksList, completed_orders, all_orders_completed, slArray, PlaceQtyForEachStockArray, Stock_Symbols, Stock_Tokens
    exchange = 'NSE'

    ret = api.get_positions()
    if ret is None:
        print("No positions found.")
        all_orders_completed = True  # Indicate no positions found, stopping scheduler
        if scheduler:
            scheduler.stop()  # Stop the scheduler
        return

    mtm = 0
    pnl = 0
    for i in ret:
        mtm += float(i['urmtom'])
        pnl += float(i['rpnl'])
    day_m2m = mtm + pnl

    if day_m2m <= -220 and not all_orders_completed:
        print('Executed_allSL')
        for i, symbol in enumerate(stocksList):
            try:
                index = Stock_Symbols.index(symbol)
                tokenForStock = Stock_Tokens[index]
                api.place_order(buy_or_sell='S', product_type='I', exchange=exchange, tradingsymbol=tokenForStock,
                                quantity=PlaceQtyForEachStockArray[i], discloseqty=0, price_type='MKT',
                                trigger_price=None, retention='DAY', remarks='stop_loss_order')
            except ValueError:
                print(f"Symbol {symbol} not found in the list.")
            except Exception as e:
                print(f"Error occurred for symbol {symbol}: {e}")

        all_orders_completed = True  # Indicate all stop-loss orders are placed
        if scheduler:
            scheduler.stop()  # Stop the scheduler
        return  # Exit the function after placing stop-loss orders

    for i, symbol in enumerate(stocksList):
        try:
            targetPrice = round((slArray[i] * 1.008), 2)
            stopLoss = round((slArray[i] * 0.9955), 2)
            stopLossFinal = round(float(stopLoss) * 10) / 10
            targetPriceFinal = round(float(targetPrice) * 10) / 10

            index = Stock_Symbols.index(symbol)
            tokenForStock = Stock_Tokens[index]
            quote = api.get_quotes(exchange=exchange, token=tokenForStock)
            LTP = float(quote["lp"])

            if (LTP <= stopLossFinal) or (LTP >= targetPriceFinal):
                api.place_order(buy_or_sell='S', product_type='I', exchange=exchange, tradingsymbol=tokenForStock,
                                quantity=PlaceQtyForEachStockArray[i], discloseqty=0, price_type='MKT',
                                trigger_price=None, retention='DAY', remarks='stop_loss_order')
                print(f"Stop loss triggered for symbol: {symbol} at price: {slArray[i]}")
                completed_orders.append(symbol)
            else:
                continue

        except ValueError:
            print(f"Symbol {symbol} not found in the list.")
        except Exception as e:
            print(f"Error occurred for symbol {symbol}: {e}")

    for symbol in completed_orders:
        index = stocksList.index(symbol)
        stocksList.pop(index)
        slArray.pop(index)
        PlaceQtyForEachStockArray.pop(index)

    completed_orders.clear()

    if not stocksList:
        all_orders_completed = True
        if scheduler:
            scheduler.stop()  # Stop the scheduler




# Initialize the scheduler
scheduler = BackgroundScheduler()

def execute_strategy_job():
    # Run the execute_strategy function
    execute_strategy()
    # After execute_strategy completes, start scheduling book_orders every 10 seconds
    scheduler.add_job(book_orders, 'interval', seconds=10, id='book_orders_job', kwargs={'scheduler': scheduler})

# Schedule execute_strategy to run at 10:06 AM every day
scheduler.add_job(execute_strategy_job, 'cron', hour=21, minute=00, id='execute_strategy_job')

# Start the scheduler
scheduler.start()

# Ensuring graceful shutdown
try:
    while True:
        time.sleep(2)
except (KeyboardInterrupt, SystemExit):
    scheduler.shutdown()