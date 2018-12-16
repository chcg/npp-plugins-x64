# -*- coding: utf-8 -*-

import json
try:
    from lxml import etree
except ImportError:
    import xml.etree.cElementTree as etree
import os
import io
import sys
import requests
import zipfile
from hashlib import md5
from jsonschema import Draft4Validator, FormatChecker
import win32api
from win32api import GetFileVersionInfo, LOWORD, HIWORD

api_url = os.environ.get('APPVEYOR_API_URL')
has_error = False


def get_version_number(filename):
    info = GetFileVersionInfo(filename, "\\")
    ms = info['FileVersionMS']
    ls = info['FileVersionLS']
    return '.'.join(map(str, [HIWORD(ms), LOWORD(ms), HIWORD(ls), LOWORD(ls)]))

def post_error(message):
    global has_error

    has_error = True

    message = {
        "message": message,
        "category": "error",
        "details": ""
    }

    if api_url:
        requests.post(api_url + "api/build/messages", json=message)
    else:
        from pprint import pprint
        pprint(message)

# validate xml against a schema
def validateXML(xml_file, xsd_file):
	print('XML schema for validation metadata: ' + xsd_file)
	schema = etree.XMLSchema( etree.parse( xsd_file ) )
	try:
		xml_tree = etree.parse( xml_file )
		schema.assertValid(xml_tree)
		print('Validating metadata against XML schema\tOK')
	except etree.XMLSyntaxError as error:
		print('Validating metadata against XML schema\tERROR XML Syntax Error. Document cannot be parsed.\n ' + str(error.error_log))
		post_error("validateXML - " + str(error))

	except etree.DocumentInvalid as error:
		print('Validating metadata against XML schema\tERROR Document Invalid Exception.\n ' + str(error.error_log))
		post_error("validateXML - " + str(error))


def parse(xmlfilename, filename):

    try:
        schema = json.loads(open("pl.schema").read())
        schema = Draft4Validator(schema, format_checker=FormatChecker())
    except ValueError as e:
        post_error("pl.schema - " + str(e))
        return

    try:
        pl = json.loads(open(filename).read())
    except ValueError as e:
        post_error(filename + " - " + str(e))
        return

    for error in schema.iter_errors(pl):
        post_error(error.message)

    xml_root = etree.parse( xmlfilename )

    os.mkdir("./" + bitness_from_input)
    for plugin in xml_root.findall( "plugin" ):
        pluginname = plugin.get("name")
        print(pluginname)

        pluginDownloadLocation = plugin.findtext( ".//download" )
        print(pluginDownloadLocation)

        try:
            response = requests.get(pluginDownloadLocation)
        except requests.exceptions.RequestException as e:
            post_error(str(e))
            continue

        if response.status_code != 200:
            post_error(f'{pluginname}: failed to download plugin. Returned code {response.status_code}')
            continue

        # Hash it and make sure its what is expected
        #hash = sha256(response.content).hexdigest()
        #if plugin["id"].lower() != hash.lower():
        #    post_error(f'{pluginname}: Invalid hash. Got {hash.lower()} but expected {plugin["id"]}')
        #    continue

        # Make sure its a valid zip file
        try:
            zip = zipfile.ZipFile(io.BytesIO(response.content))
        except zipfile.BadZipFile as e:
            post_error(f'{pluginname}: Invalid zip file')
            continue

        # The expected DLL name
        # TODO check how to find dll name from pluginname
        dll_name = f'{pluginname}.dll'.lower()

        # Notepad++ is not case sensitive, but extracting files from the zip is,
        # so find the exactfile name to use
        for file in zip.namelist():
            if dll_name == file.lower():
                dll_name = file
                break
        else:
            post_error(f'{pluginname}: Zip file does not contain {dll_name}')
            continue

        with zip.open(dll_name) as dll_file, open("./" + bitness_from_input + "/" + dll_name, 'wb') as f:
            f.write(dll_file.read())

        version = plugin.findtext( "x64Version" )
        print(version)

        # Fill in any of the missing numbers as zeros
        version = version + (3 - version.count('.')) * ".0"

        try:
            dll_version = get_version_number("./" + bitness_from_input + "/" + dll_name)
        except win32api.error:
            post_error(f'{pluginname}: Does not contain any version information')
            continue

        if dll_version != version:
            post_error(f'{pluginname}: Unexpected DLL version. DLL is {dll_version} but expected {version}')
            continue


bitness_from_input = sys.argv[1]
print('input: %s' % bitness_from_input)
if bitness_from_input == 'x64':
    validateXML("plugins/plugins64.xml", "plugins/plugins64.xsd")
    parse("plugins/plugins64.xml", "plugins/validate.json")
else:
    #validateXML("plugins/plugins32.xml", "plugins/plugins32.xsd")
    parse("plugins/plugins32.xml", "plugins/validate.json")

if has_error:
    sys.exit(-2)
else:
    sys.exit()
