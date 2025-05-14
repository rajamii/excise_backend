import random
import time

# OTP Class to represent an OTP (One Time Password)
class OTP:
    phone_number: str  # The phone number for which the OTP is generated
    otp: int           # The OTP value (4-digit number)
    index: int         # Unique index for the OTP
    used: bool         # Flag to check if the OTP has been used
    created_on: int    # Timestamp when the OTP was created

    # Method to check if the OTP has been used
    def is_used(self):
        return self.used

    # Method to get the creation time of the OTP
    def get_creation_time(self):
        return self.created_on

    # Method to check if the provided OTP, phone number, and index match the stored OTP
    def check_otp(self, in_otp, in_phone_number, in_index):
        return in_otp == self.otp and in_phone_number == self.phone_number and in_index == self.index

    # Method to generate a new OTP for a given phone number and index
    @staticmethod
    def gen_otp(phone_number, index):
        retval = OTP()  # Create a new OTP object

        # Set attributes: phone number, random OTP, index, used flag (False), and creation time
        retval.phone_number = phone_number
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

    # Method to generate and return a new OTP for a given phone number
    def get_new_otp(self, in_phone_number):
        otp = OTP.gen_otp(phone_number=in_phone_number, index=self.index)  # Generate OTP
        self.index += 1  # Increment the index
        self.otplist.append(otp)  # Add OTP to the list
        return otp

    # Method to check the time for all OTPs and mark expired ones as used
    def check_time_and_mark(self):
        if not self.otplist:  # If no OTPs in the list, return early
            return

        current_time = time.time()  # Get current time

        # Loop through the OTP list and mark expired OTPs as used
        for otp in self.otplist:
            elapsed_time = current_time - otp.get_creation_time()
            if elapsed_time > 600:  # If OTP is older than 600 seconds (10 minutes)
                otp.used = True

    # Method to clean up the OTP list if all OTPs are used
    def cleanup(self):
        # Check if all OTPs in the list have been used
        if all(otp.is_used() for otp in self.otplist):
            self.otplist.clear()
            self.index = 0
