## Invoice Extraction App

Invoice Extraction App

#### License

mit

installiation

bench get-app https://github.com/waddah82/invoice_extraction_app

source env/bin/activate

pip install google-generativeai pillow requests python-dotenv

deactivate

bench --site [site name] install-app invoice_extraction_app



goto  https://site name/app/gemini-settings/Gemini%20Settings
<img width="1170" height="568" alt="image" src="https://github.com/user-attachments/assets/ee7f96ba-7fa1-46ec-8e47-8af881152373" />
get api key from google 

goto  https://site name/app/extracted-invoice    
add extracted invoice 
upload pdf/image file
press extract buttom 
