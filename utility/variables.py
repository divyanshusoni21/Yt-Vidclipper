import pytz
from yt_helper.settings import ADMIN_EMAIL,FRONTEND_URL,ADMIN_PHONE,BREVO_API_KEY
import re

istTimezone = pytz.timezone('Asia/Kolkata')
utcTimezone = pytz.timezone('utc')

# from home.models import ProjectInfo
# try:
#     project_info = ProjectInfo.objects.first()
# except Exception as e:

#     project_info = None

projectName = 'YT HELPER'
adminEmail = ADMIN_EMAIL

# adminPhone = project_info.admin_phone if project_info else ADMIN_PHONE

frontendDomain = FRONTEND_URL

# backendDomain =  project_info.backend_domain if project_info else "http://127.0.0.1:8000"

brevoApiKey = BREVO_API_KEY

# loginPath = "/login"

# s3ObjectExpirationTimeInSeconds=3600


# projectLogo = project_info.project_logo.url if project_info and project_info.project_logo else ""
# if not projectLogo.startswith("http"):
#     projectLogo = f"{backendDomain}/{projectLogo}" if project_info else "https://i.ibb.co/YY68cfQ/trueclean-logo.png"


# whatsappCTAUrl = project_info.whatsapp_cta_url if project_info and project_info.whatsapp_cta_url else "https://api.whatsapp.com/send/?phone=919316999874&text=Hello%21+I%27m+interested+in+your+cleaning+services.&type=phone_number&app_absent=0"



# downloadIcon="https://dev.diyafaco.com/assets/download_icon.png"
# viewIcon="https://dev.diyafaco.com/assets/view_icon.png"
