#! /usr/bin/python3
class Installer():
    def __init__(self):
        # Default names:
        self.target_folder = "python_modules"
        self.project_name = "project.zip"
        self.exec_policy = "-lambda-exec-policy"
        self.function_name = "lambda_function"
        self.function_handler = "lambda_handler"

        # Loading basic config:
        if os.path.isfile("lambda_config.yml"):
            with open("lambda_config.yml", "r") as file: config = yaml.full_load(file)
            self.modules = config["python"]["requirements"]
            self.runtime = config["python"]["runtime"]
            self.name = config["function"]["name"]
            self.handler = config["function"]["handler"]
            self.config_exisists = True
        else:
            self.config_exisists = False

    # Private methods:
    def __detect_config(function):
        def wrapper(*args, **kwargs):
            if args[0].config_exisists:
                return function(*args, **kwargs)
            else:
                print("No config file was detected, please build one or run the command again with the -b parameter")
                quit()
        return wrapper

    def __execute(self, command):
        os.system(f"{command} > cmd.out")
        with open("cmd.out", "rb") as json_file:
            response = json.loads(json_file.read())
        os.system("rm cmd.out")
        return response
        
    # Method to build an initial config:
    def build(self):
        # Build the template for the config:
        with open("lambda_config.yml", "w") as file:
            file.write(f"python:\n  runtime: python3.9\n  requirements:\n    - requests\nfunction:\n  name: example\n  handler: {self.function_name}.{self.function_handler}")

        # Build the base python template:
        with open(f"{self.function_name}.py", "w") as file:
            file.write(f"#! /usr/bin/python3\n\ndef {self.function_handler}(event, context):\n\treturn event")

    @__detect_config
    def install_modules_locally(self):
        # Fistly check if the target folder exists:
        if os.path.exists(os.path.join(os.getcwd(), self.target_folder)):
            os.system(f"rm -rf {self.target_folder}")

        # If it doesen't create a python modules folder and amplify its scope:
        print("Modules file not detected, creating it:\n")
        folder = f'{os.getcwd()}/{self.target_folder}'
        os.mkdir(folder)

        print("Creating __init__.py to amplify the path \n")
        with open(f'{folder}/__init__.py', "w") as file:
            file.write("#! /usr/bin/python3\nimport sys\nsys.path.append(f'{sys.path[0]}/python_modules')")


        # Check for the distribution:
        print("Installing modules:\n")
        for module in self.modules:
            os.system(f"pip3 install -t {folder} {module} 1>/dev/null")
            print(f"\t- Installing: {module}")

        # Clearing dist files:
        for dir in os.listdir(f"{os.getcwd()}/{self.target_folder}"):
            if "dist-info" in dir:
                os.system(f"rm -rf {os.getcwd()}/{self.target_folder}/{dir}")

        print("\n\nFinalized installation process. Remember to import python_modules in every used script to access the modules!\n")


    @__detect_config
    def upload(self):
        print("Compressing and uploading the file to the cloud \n")
        # Compressing the project:
        os.system(f"zip -qr {self.project_name} *")

        #Upload:
        os.system(f"aws lambda update-function-code --function-name {self.name} --zip-file fileb://{self.project_name}")

        # Deleting the zip:
        os.system(f"rm {self.project_name}")


    @__detect_config
    def create(self):
        print("Creating new function:")
        # Checking if the execution policy has already been created:
        response = self.__execute("aws iam list-roles")
        roles = response['Roles']
        role_created = False
        for role in roles:
            if role['RoleName'] == f"{self.name}{self.exec_policy}":
                print("\tThere is already a role created with that name, would you like to use it to create the lambda?")
                while True:
                    user_selection = input("\n\tYes(y), No(n): ")
                    if user_selection == "n":
                        quit()
                    if user_selection == "y":
                        role_created = True
                        function_role = role['Arn']
                        break
                    else:
                        print("\tjust type 'y' or 'n'...")

        if role_created == False:
            # Creation of the execution policy:
            print("\t- Creation of the role required")
            execution_policy = '{"Version": "2012-10-17","Statement": [{ "Effect": "Allow", "Principal": {"Service": "lambda.amazonaws.com"}, "Action": "sts:AssumeRole"}]}'
            command =  f"aws iam create-role --role-name {self.name}{self.exec_policy} --assume-role-policy-document '{execution_policy}' >> cmd.out"
            response = self.__execute(command)
            function_role = response['Role']['Arn']

            # Attach the role policy:
            print("\t- Attaching the lambda execution policy to the new created role, this process may take a while")
            os.system(f"aws iam attach-role-policy --role-name {self.name}{self.exec_policy} --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole")
            time.sleep(5)

        # Create the function:
        print("\t- Compressing and uploading the file to the cloud\n")
        os.system(f"zip -qr {self.project_name} *")
        os.system(f"aws lambda create-function --function-name {self.name} --zip-file fileb://{self.project_name} --handler {self.handler} --runtime {self.runtime} --role {function_role}")

        # Deleting the zip:
        os.system(f"rm {self.project_name}")


    @__detect_config
    def run(self):
        command = f"aws lambda invoke --function-name {self.name} out --log-type Tail"
        response = self.__execute(command)
        print("Output")
        print(f"\tStatusCode: {response['StatusCode']}")
        print(f"\tLog:\n\t{base64.b64decode(response['LogResult']).decode()}")


    @__detect_config
    def delete(self):
        os.system(f"aws lambda delete-function --function-name {self.name}")
        

if __name__ == "__main__":
    import sys, os, subprocess, json, time, base64

    # Check for yaml & if not installed, install it:
    output = subprocess.run("pip3 freeze | grep PyYAML", shell=True, capture_output=True, text=True).stdout
    if output == "":
        print("Missing dependency (pyyaml), installing it...\n")
        os.system("pip3 install pyyaml 1>/dev/null")

    import yaml

    # Importing the class:
    installer = Installer()
    for command in sys.argv[1:]:
        if "-i" in command:
            installer.install_modules_locally()

        elif "-u" in command:
            installer.upload()

        elif "-c" in command:
            installer.create()

        elif "-r" in command:
            installer.run()

        elif "-d" in command:
            installer.delete()

        elif "-b" in command:
            installer.build()

        elif "-h" in command:
            print("This function accepts the following parameters:")
            print("\t-i to install the modules specified in the lambda_config.yml file")
            print("\t-u to upload the already existing lambda function to the cloud")
            print("\t-c to creates a lambda function based on lambda_config.yml file & uploads the current dir to AWS")
            print("\t-r to run the lambda funtion")
            print("\t-d to delete the current function")
            print("\t-b to create an starting template")

        else:
            print("Command not found, please use -h or --help to get information about the function")

