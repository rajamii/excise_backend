"""
Custom exception class for SBI ePay SDK.
"""

class SBIEpayException(Exception):
    """
    Custom exception for SBI ePay SDK operations.
    Supports multiple constructor patterns similar to Java/PHP implementations.
    """
    
    def __init__(self, *args):
        """
        Initialize SBIEpayException with flexible parameters.
        
        Patterns:
        - SBIEpayException(message: str)
        - SBIEpayException(status_code: int, message: str)
        - SBIEpayException(status_code: int, message: str, cause: Exception)
        - SBIEpayException(cause: Exception)
        """
        if len(args) == 1:
            if isinstance(args[0], Exception):
                # SBIEpayException(cause: Exception)
                super().__init__(str(args[0]))
                self.cause = args[0]
                self.status_code = None
            else:
                # SBIEpayException(message: str)
                super().__init__(args[0])
                self.cause = None
                self.status_code = None
                
        elif len(args) == 2:
            # SBIEpayException(status_code: int, message: str)
            # self.status_code = args[0]
            self.status_code = 400
            message = f"Status Code: {args[0]}\nServer response: {args[1]}"
            super().__init__(message)
            self.cause = None
            
        elif len(args) == 3:
            # SBIEpayException(status_code: int, message: str, cause: Exception)
            # self.status_code = args[0]
            self.status_code = 400
            message = f"Status Code: {args[0]}\nServer response: {args[1]}"
            super().__init__(message)
            self.cause = args[2]
            
        else:
            super().__init__("Something went wrong with exception!")
            self.cause = None
            self.status_code = None
    
    def get_status_code(self):
        """Get the status code if available."""
        return self.status_code
    
    def get_cause(self):
        """Get the underlying cause exception if available."""
        return self.cause