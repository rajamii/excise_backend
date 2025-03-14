#!/bin/bash

venv_dir="./virt"

if [ "$1" == "make_virt" ];
then
  python3 -m venv virt

elif [ "$1" == "install" ];
then 

 source ./virt/bin/activate &&
 "$venv_dir/bin/pip" install asgiref                        &&      
 "$venv_dir/bin/pip" install captcha                        &&        
 "$venv_dir/bin/pip" install certifi                        &&     
 "$venv_dir/bin/pip" install charset-normalizer             &&        
 "$venv_dir/bin/pip" install Django                         &&    
 "$venv_dir/bin/pip" install django-cors-headers            &&         
 "$venv_dir/bin/pip" install django-ranged-response         &&   
 "$venv_dir/bin/pip" install django-simple-captcha          &&        
 "$venv_dir/bin/pip" install djangorestframework            &&               
 "$venv_dir/bin/pip" install djangorestframework_simplejwt  &&               
 "$venv_dir/bin/pip" install idna                           &&                   
 "$venv_dir/bin/pip" install pillow                         &&               
 "$venv_dir/bin/pip" install psycopg                       &&              
 "$venv_dir/bin/pip" install psycopg2-binary                &&         
 "$venv_dir/bin/pip" install PyJWT                          &&           
 "$venv_dir/bin/pip" install requests                       &&                
 "$venv_dir/bin/pip" install sqlparse                       &&               
 "$venv_dir/bin/pip" install tzdata                         &&              
 "$venv_dir/bin/pip" install urllib3


elif [ "$1" == "test" ];
then
  "$venv_dir/bin/python3" manage.py runserver
fi
