# This is the documentation on api end points for the excise department website official backend 

## Api endpoints provided by excise_app


| URL Pattern                                | View Class/Function             | Request Type(s) | Functionality                                                                  |
| ------------------------------------------ | ------------------------------- | --------------- | ------------------------------------------------------------------------------ |
| `register/`                                | `UserRegistrationView`          | POST            | Registers a new user and returns the generated username.                    |
| `login/`                                   | `UserLoginView`                 | POST            | Authenticates a user with username and password, returns JWT tokens.        |
| `send_otp/`                                | `SendOTP`                       | POST            | Sends an OTP to the provided phone number.                                    |
| `otp_login/`                               | `OTPLoginView`                  | POST            | Authenticates a user with phone number and OTP, returns JWT tokens.            |
| `get_captcha/`                             | `get_captcha`                   | GET             | Generates and returns a CAPTCHA image and hash key.                           |
| `userdetails/`                             | `UserDetails`                   | GET             | Retrieves details of the authenticated user.                                    |
| `district/`                                | `DistrictAdd`                   | POST            | Creates a new District.                                                        |
| `district/<int:id>/`                       | `DistrictAdd`                   | PUT             | Updates an existing District's `IsActive` status.                               |
| `district/view/`                           | `DistrictView`                  | GET             | Retrieves a list of all Districts or a specific District by ID.              |
| `subdivision/`                             | `SubDivisonApi`                 | POST            | Creates a new Subdivision.                                                     |
| `subdivision/<int:id>/`                    | `SubDivisonApi`                 | PUT             | Updates an existing Subdivision.                                                 |
| `subdivision/view/`                        | `SubdivisionView`               | GET             | Retrieves a list of all Subdivisions or a specific Subdivision by ID.        |
| `subdivision/by-district-code/<int:district_code>/` | `GetSubdivisionByDistrictCode` | GET             | Retrieves Subdivisions by a provided district code.                     |
| `dashboard/`                               | `DashboardCountView`            | GET             | Retrieves dashboard counts (e.g., district and subdivision counts).             |


## Api endpoints provided by masters 

| URL Pattern                  | View Class                 | Request Type(s) | Functionality                                                           |
| ---------------------------- | -------------------------- | --------------- | ----------------------------------------------------------------------- |
| `license-categories/`        | `LicenseCategoryList`      | GET, POST       | Lists all license categories and creates a new license category.        |
| `license-type/`              | `LicenseTypeList`          | GET, POST       | Lists all license types and creates a new license type.                 |
| `subdivision/`               | `SubDivisonApi`            | POST            | Creates a new subdivision.                                              |
| `subdivision/<int:pk>/`      | `SubDivisonApi`            | GET, PUT        | Retrieves or updates a specific subdivision.                            |
| `district/`                  | `DistrictAdd`              | POST            | Creates a new district.                                                 |
| `district/<int:id>/`         | `DistrictAdd`              | PUT             | Updates a specific district.                                            |
| `districts/`                 | `DistrictView`             | GET             | Lists all districts.                                                    |
| `districts/<int:pk>/`        | `DistrictView`             | GET             | Retrieves a specific district.                                          |
| `policestation/`             | `PoliceStationAPI`         | POST            | Creates a new police station.                                           |
| `policestation/<int:id>/`    | `PoliceStationAPI`         | PUT             | Updates a specific police station.                                      |
| `policestations/`            | `PoliceStationAPI`         | GET             | Lists all police stations.                                              |
| `policestations/<int:pk>/`   | `PoliceStationAPI`         | GET             | Retrieves a specific police station.                                    |


## Api endpoints provided by salesman_barman


| URL Pattern                        | View Class                 | Request Type(s) | Functionality                                     |
| ---------------------------------- | -------------------------- | --------------- | ------------------------------------------------- |
| `salesman_barman/`                 | `SalesmanBarmanView`       | POST            | Creates a new Salesman_barman                     |
| `salesman_barman/<int:sb>/`        | `SalesmanBarmanView`       | GET             | List a specific police station                    |
| `salesman_barmans/<int:id>/`       | `SalesmanBarmanView`       | PUT             | Updates a specific police station                 |
| `salesman_barmans/`                | `SalesmanBarmanView`       | GET             | Lists all salesman_barman                         |
