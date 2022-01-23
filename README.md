# Introduction:
This project is developed to automate uploading lambda functions to AWS. Additionally, it builds a folder structure to keep the least amount of modules in your project and separates the main modules into  a subfolder called **python_modules**.

To upload the project to github you can easily exclude all the modules that go into the repo by ignoring this folder.

The only catch is that to import any installed module you will need to import python_modules in all modules.

# Usage:
The current project has the hability to create, delete and upload python projects to AWS lambda service. Additionally, it helps with the organization of python imports.
* To install the modules listed in the config file locally, just run:
```bash
python3 compile.py -i
```

* To build the config files automatically run:
```bash
python3 compile.py -b
```

* To create a lambda function from the base config run. **This may not work the first time**, as the activation of the roles takes time. Just run the same command again.
```bash
python3 compile.py -c
```

* To upload the project to an already existing lambda: (**IMPORTANT**: Remember to pick the right name and handler in the config file! )
```bash
python3 compile.py -u
```

* To delete a function run:
```bash
python3 compile.py -d
```

* To run the function and see the output:
```bash
python3 compile.py -r
```

* There is a -h flag in case you forgot something!

# Example Config:
You will need a lambda_config.yml to run and upload the file. If you prefer not to create it automatically just copy paste this one.
```yaml
python:
  runtime: 3.9
  requirements:
    - requests
function:
  name: example
  handler: lambda_function.lambda_handler
```

# Usage as a command **not recommended**:
Move the compile.py to /usr/bin/ and create a symlink:
```bash
sudo cp compile.py /usr/bin
cd /usr/bin
sudo ln -s compile.py the_name_you_want
```
The symlink was created as sudo. The user can write bash scripts in the config file and run commands with root permissions!

# To do:
* Review security issues, too much os.system being used. The idea is to have it run as a regular binary but now it cant be used as root. 
* Research the timing issue when creating the functions
