import random
import time

class OTP :

    def __init__(self, username: str, otp: int, index: int):

        self.username = username
        self.otp = otp
        self.index = index
        self.used = False
        self.created_on = time.time()

    def is_used(self):

        return self.used

    def get_creation_time(self):

        return self.created_on

    @staticmethod
    def check_otp(in_otp , in_username , in_index ):

        used = True

        if in_otp == otp and in_username == username and in_index == index :

            return True

        return False

    @staticmethod
    def gen_otp(username , index):
        return OTP(username , random.randint(1000 , 9999 ) , index)
    


class OTPLIST:

    def __init__(self):

        self.otplist = []
        self.index = 0


    def get_new_otp(self , in_username ):

        otp = OTP.gen_otp(username=in_username , index=self.index)
        self.index = self.index + 1;
        self.otplist.append(otp)
        return otp

    def check_time_and_mark(self ):

        if len(self.otplist) > 1: 

            current_time = time.time()
    
            for i in self.otplist:
    
                elapsed_time = current_time - i.get_creation_time()
    
                if elapsed_time > 600 :
    
                    i.used = True

        


    def cleanup(self) -> None:
        if not self.otplist:
            return
        if all(otp.is_used() for otp in self.otplist):
            self.otplist.clear()
            self.index = 0            
