from functools import wraps
from flask import Flask, request, jsonify
from flask_cors import CORS
from cachetools import TTLCache
import lib2
import json
import asyncio
import traceback
import re


print("🔄 جاري تحميل البيانات الأولية...")
try:
    lib2.fetch_latest_data()
    print("✅ تم تحميل البيانات بنجاح")
except Exception as e:
    print(f"❌ فشل تحميل البيانات: {e}")
    print("⚠️ قد لا تعمل بعض الميزات بشكل صحيح")


app = Flask(__name__)
CORS(app)

cache = TTLCache(maxsize=100, ttl=300)

def cached_endpoint(ttl=300):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            cache_key = (request.path, tuple(request.args.items()))
            if cache_key in cache:
                return cache[cache_key]
            else:
                result = func(*args, **kwargs)
                cache[cache_key] = result
                return result
        return wrapper
    return decorator

@app.route('/info=<uid>')
@cached_endpoint()
def get_account_info(uid):    

    if not uid or not uid.isdigit():
        response = {
            "error": "Invalid request",
            "message": "Invalid 'uid' parameter. Please provide a valid numeric UID."
        }
        return jsonify(response), 400, {'Content-Type': 'application/json; charset=utf-8'}

    try:
        print(f"🔍 محاولة جلب معلومات اللاعب: UID={uid} (بحث مع أولوية ME)")
        
        if lib2.current_payload_template is None:
            print("⚠️ البيانات غير محملة، جاري التحميل...")
            lib2.fetch_latest_data()
        
        supported_regions = ["ME"]
        
        for region in supported_regions:
            try:
                print(f"🔎 البحث في السيرفر: {region}")
                return_data = asyncio.run(lib2.GetAccountInformation(uid, "7", region, "/GetPlayerPersonalShow"))
                
                if return_data and not return_data.get("error"):
                    print(f"✅ تم العثور على اللاعب في السيرفر: {region}")
                    formatted_json = json.dumps(return_data, indent=2, ensure_ascii=False)
                    return formatted_json, 200, {'Content-Type': 'application/json; charset=utf-8'}
                    
            except Exception as e:
                print(f"❌ اللاعب غير موجود في السيرفر {region}: {str(e)}")
                continue
        
        response = {
            "error": "Player not found",
            "message": f"Player with UID {uid} was not found in any supported region."
        }
        return jsonify(response), 404, {'Content-Type': 'application/json; charset=utf-8'}
        
    except Exception as e:
        print(f"❌ خطأ تفصيلي في API:")
        print(f"   الخطأ: {str(e)}")
        print(f"   نوع الخطأ: {type(e).__name__}")
        print(f"   تفاصيل الخطأ:")
        traceback.print_exc()
        
        response = {
            "error": "Connection failed",
            "message": f"Unable to connect to Free Fire servers: {str(e)}",
            "error_type": type(e).__name__
        }
        return jsonify(response), 503, {'Content-Type': 'application/json; charset=utf-8'}

@app.route('/')
def home():
    return "Free Fire API is running!"

@app.route('/health')
def health_check():
    status = {
        "status": "running",
        "data_loaded": lib2.current_payload_template is not None,
        "server_domain": lib2.current_server_domain,
        "release_version": lib2.current_release_version,
        "play_version": lib2.current_play_version
    }
    return jsonify(status)

if __name__ == '__main__':
    print("\n" + "="*50)
    print("🚀 تشغيل خادم Free Fire API")
    print("="*50)
    print(f"📡 المنفذ: 13522")
    print(f"🌐 العنوان: http://0.0.0.0:13522")
    print(f"🔗 رابط الصحة: http://localhost:13522/health")
    print("="*50 + "\n")
    
    app.run(port=13522, host='0.0.0.0', debug=True)