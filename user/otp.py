import random
import time

class OTP :

    username   : str 
    otp        : int 
    index      : int 
    used       : bool
    created_on : int 


    def is_used(self):

        return self.used

    def get_creation_time(self):

        return self.created_on

    def check_otp(in_otp , in_username , in_index ):

        used = True

        if in_otp == otp and in_username == username and in_index == index :

            return True

        return False



    def gen_otp(username , index):

        retval = OTP;

        retval.username = username
        retval.otp = random.randint(1000,9999)
        retval.index = index 
        retval.used = False
        retval.created_on = time.time

        return retval
    


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

        if len(self.otplist) < 0: 
            return
        

        current_time = time.time()

        for i in self.otplist:

            elapsed_time = current_time - i.get_creation_time()

            if elapsed_time > 600 :

                i.used = True

    def cleanup(self):

        cleanup_ok = True

        for i in self.otplist:
            if i.is_used == false :

                cleanup_ok = False
                break

        if cleanup_ok == True :
            self.otplist.clear()
            self.index = 0


            
