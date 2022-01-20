# Introduction:
This project is developed to automate uploading lambda functions to AWS. Additionally, it builds a folder structure to keep the least amount of modules in your project and separates the main modules into  a subfolder called *python_modules*.

To upload the project to github you can easily exclude all the modules that go into the repo by ignoring this folder.

The only catch is that to import any installed module you will need to import python_modules in all modules.

# Installation:
You will need a lambda_config.yml built with at least the python modules config specified:
```yaml
python:
  runtime: 3.9
  requirements:
    - pyjwt
    - requests
    - cryptography
```

To install modules locally, just run:
```bash
python3 compile.py
```
If you also want to upload the project to a lambda function include **upload** in the command:
```bash
python3 compile.py upload
```
# To do:
Implement creation of lambda functions!
