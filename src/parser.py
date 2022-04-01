import json
import datetime
from datetime import timedelta
import requests
from flask import current_app, request
from slugify import slugify

region_field = "region"

def parser():
    output = {}
    data = {}
    result_json = None

    spreadsheet_id = current_app.config["SPREADSHEET_ID"]
    worksheet_names = current_app.config["WORKSHEET_NAMES"]
    cache_timeout = int(current_app.config["API_CACHE_TIMEOUT"])
    store_in_s3 = current_app.config["STORE_IN_S3"]
    bypass_cache = request.args.get("bypass_cache", "false")
    if store_in_s3 == "true":
        bypass_cache = request.args.get("bypass_cache", "true")
    if spreadsheet_id is not None:
        api_key = current_app.config["API_KEY"]
        authorize_url = current_app.config["AUTHORIZE_API_URL"]
        url = current_app.config["PARSER_API_URL"]
        if authorize_url != "" and api_key != "" and url != "":
            token_params = {
                "api_key": api_key
            }
            token_headers = {"Content-Type": "application/json"}
            token_result = requests.post(authorize_url, data=json.dumps(token_params), headers=token_headers)
            token_json = token_result.json()
            if token_json["token"]:
                token = token_json["token"]
                authorized_headers = {"Authorization": f"Bearer {token}"}
                worksheet_slug = '|'.join(worksheet_names)
                result = requests.get(f"{url}?spreadsheet_id={spreadsheet_id}&worksheet_names={worksheet_slug}&external_use_s3={store_in_s3}&bypass_cache={bypass_cache}", headers=authorized_headers)
                result_json = result.json()
    
        if result_json is not None:
            if "customized" in result_json and bypass_cache == "false":
                output = json.dumps(result_json, default=str)
            else:
                house = result_json["House"]
                senate = result_json["Senate"]
                categories = result_json["Categories"]

                if house is not None or senate is not None:
                    data["candidates"] = []

                if house is not None:
                    for candidate in house:
                        candidate = format_candidate(candidate, 'house', categories)
                        # add to the returnable data
                        if candidate != None:
                            data["candidates"].append(candidate)

                if senate is not None:
                    for candidate in senate:
                        candidate = format_candidate(candidate, 'senate', categories)
                        # add to the returnable data
                        if candidate != None:
                            data["candidates"].append(candidate)
                
                # set metadata and send the customized json output to the api
                if "generated" in result_json:
                    data["generated"] = result_json["generated"]
                data["customized"] = datetime.datetime.now()
                if cache_timeout != 0:
                    data["cache_timeout"] = data["customized"] + timedelta(seconds=int(cache_timeout))
                else:
                    data["cache_timeout"] = 0
                if bypass_cache == "false" and ("customized" not in result_json or store_in_s3 == "true"):
                    bypass_cache = "true"
                    if "customized" in data and store_in_s3 == "false":
                        bypass_cache = "false"
                output = json.dumps(data, default=str)
            if "customized" not in result_json or store_in_s3 == "true":
                overwrite_url = current_app.config["OVERWRITE_API_URL"]
                params = {
                    "spreadsheet_id": spreadsheet_id,
                    "worksheet_names": worksheet_names,
                    "output": output,
                    "cache_timeout": cache_timeout,
                    "bypass_cache": bypass_cache,
                    "external_use_s3": store_in_s3
                }

                headers = {"Content-Type": "application/json"}
                if authorized_headers:
                    headers = headers | authorized_headers
                result = requests.post(overwrite_url, data=json.dumps(params), headers=headers)
                result_json = result.json()
                if result_json is not None:
                    output = json.dumps(result_json, default=str)

    else:
        output = {} # something for empty data
    return output


def format_candidate(candidate, chamber, categories):
    # add the district id
    if candidate["district"] != None and candidate["name"] != None:
        candidate["district"] = str(candidate["district"])
        candidate["chamber"] = chamber
        for category in categories:
            if str(category["district"]) == str(candidate["district"]):
                region = category[region_field]
                break
        else:
            region = None
        if region != None:
            candidate["region"] = region
            candidate["region-id"] = slugify(candidate["region"], to_lower=True)
        #candidate["district-id"] = slugify(candidate["district"], to_lower=True)
        # make an ID
        candidate_id = str(candidate["district"]).replace(" ", "").lower() + "-" + candidate["name"].replace(" ", "").lower()
        candidate["candidate-id"] = candidate_id
        # add the party id
        if candidate["party"] != None:
            candidate["party-id"] = slugify(candidate["party"], to_lower=True)
        # format the boolean fields
        candidate["incumbent?"] = convert_xls_boolean(candidate["incumbent?"])
        candidate["endorsed?"] = convert_xls_boolean(candidate["endorsed?"])
        candidate["dropped-out?"] = convert_xls_boolean(candidate["dropped-out?"])
    else:
        candidate = None
    return candidate


def convert_xls_boolean(string):
    if string == None:
        value = False
    else:
        string = string.lower()
        if string == "yes" or string == "true" or string == "y":
            value = True
        elif string == "no" or string == "false" or string == "n":
            value = False
        else:
            value = bool(string)
    return value
