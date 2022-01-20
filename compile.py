#! /usr/bin/python3

import os, sys
# Check for yaml:
os.system("pip3 freeze | grep yaml >> cmd.out")
with open("cmd.out", "r") as file: output = file.read()
if len(output) == 0:
    print("Missing dependency (pyyaml), installing it...\n")
    os.system("pip3 install pyyaml 1>/dev/null")
    os.system("rm -rf cmd.out")

import yaml


class Installer():
    def __init__(self):
        # Default names:
        self.target_folder = "python_modules"
        self.project_name = "project.zip"

        # Loading basic config:
        with open("lambda_config.yml", "r") as file: config = yaml.full_load(file)
        self.modules = config["python"]["requirements"]
        self.runtime = config["python"]["runtime"]
        self.lambda_function_name = config["function"]["name"]
        self.lambda_handler = config["function"]["handler"]
        
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
            print(f"\t+ Installing: {module}")

        # Clearing dist files:
        for dir in os.listdir(f"{os.getcwd()}/{self.target_folder}"):
            if "dist-info" in dir:
                os.system(f"rm -rf {os.getcwd()}/{self.target_folder}/{dir}")

        print("\n\nFinalized installation process. Remember to import python_modules in every used script to access the modules!\n")

    def upload(self):
        print("Compressing and uploading the file to the cloud")
        # Compressing the project:
        os.system(f"zip -qr {self.project_name} *")

        #Upload:
        os.system(f"aws lambda update-function-code --function-name {self.lambda_function_name} --zip-file fileb://{self.project_name}")

        # Deleting the zip:
        os.system(f"rm {self.project_name}")

if __name__ == "__main__":
    installer = Installer()
    installer.install_modules_locally()

    if len(sys.argv) == 2:
        if sys.argv[1] == "upload"
            installer.upload()

        if sys.argv[1] == "create"
            installer.upload()
