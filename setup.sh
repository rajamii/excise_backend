
if [ "$1" == "make_virt" ];
then
  python3 -m venv virt

elif [ "$1" == "install" ];
then 

  pip install asgiref                        &&      
  pip install captcha                        &&        
  pip install certifi                        &&     
  pip install charset-normalizer             &&        
  pip install Django                         &&    
  pip install django-cors-headers            &&         
  pip install django-ranged-response         &&   
  pip install django-simple-captcha          &&        
  pip install djangorestframework            &&               
  pip install djangorestframework_simplejwt  &&               
  pip install idna                           &&                   
  pip install pillow                         &&               
  pip install psycopg                       &&              
  pip install psycopg2-binary                &&         
  pip install PyJWT                          &&           
  pip install requests                       &&                
  pip install sqlparse                       &&               
  pip install tzdata                         &&              
  pip install urllib3


elif [ "$1" == "test" ];
then
  python3 manage.py runserver
fi
