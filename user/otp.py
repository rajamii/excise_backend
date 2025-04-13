import random
import time

# OTP Class to represent an OTP (One Time Password)
class OTP:
    username: str  # The username for which the OTP is generated
    otp: int       # The OTP value (4-digit number)
    index: int     # Unique index for the OTP
    used: bool     # Flag to check if the OTP has been used
    created_on: int # Timestamp when the OTP was created

    # Method to check if the OTP has been used
    def is_used(self):
        return self.used

    # Method to get the creation time of the OTP
    def get_creation_time(self):
        return self.created_on

    # Method to check if the provided OTP, username, and index match the stored OTP
    def check_otp(in_otp, in_username, in_index):
        if in_otp == otp and in_username == username and in_index == index:
            return True
        return False

    # Method to generate a new OTP for a given username and index
    def gen_otp(username, index):
        retval = OTP()  # Create a new OTP object

        # Set attributes: username, random OTP, index, used flag (False), and creation time
        retval.username = username
        retval.otp = random.randint(1000, 9999)  # Generate a 4-digit OTP
        retval.index = index
        retval.used = False
        retval.created_on = time.time()  # Get current timestamp

        return retval


# OTPLIST Class to manage the list of OTPs
class OTPLIST:

    # Initialize with an empty OTP list and an index for generating unique OTPs
    def __init__(self):
        self.otplist = []
        self.index = 0

    # Method to generate and return a new OTP for a given username
    def get_new_otp(self, in_username):
        otp = OTP.gen_otp(username=in_username, index=self.index)  # Generate OTP
        self.index += 1  # Increment the index
        self.otplist.append(otp)  # Add OTP to the list
        return otp

    # Method to check the time for all OTPs and mark expired ones as used
    def check_time_and_mark(self):
        if len(self.otplist) <= 0:  # If no OTPs in the list, return early
            return

        current_time = time.time()  # Get current time

        # Loop through the OTP list and mark expired OTPs as used
        for i in self.otplist:
            elapsed_time = current_time - i.get_creation_time()
            if elapsed_time > 600:  # If OTP is older than 600 seconds (10 minutes)
                i.used = True

    # Method to clean up the OTP list if all OTPs are used
    def cleanup(self):
        cleanup_ok = True  # Flag to check if all OTPs are used

        # Check if all OTPs in the list have been used
        for i in self.otplist:
            if not i.is_used():  # If there is any unused OTP
                cleanup_ok = False
                break

        # If all OTPs are used, clear the OTP list and reset the index
        if cleanup_ok:
            self.otplist.clear()
            self.index = 0
