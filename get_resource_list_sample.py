import requests
import csv
from datetime import datetime
import os

'''
対象のIBM Cloudアカウントのリソースインスタンス一覧を出力するプログラム

入力ファイル
・インスタンスごとリソース使用量csvファイル：Optional｡IBM Cloudからダウンロードしたファイルを指定｡

出力ファイル
・resource_list_yyyymmdd_hhmmss.csv：対象アカウントのリソースインスタンス一覧
・usage_list_yyyymmdd_hhmmss.csv：入力ファイルにインスタンスの作成者情報を付加したcsvファイル｡入力ファイルがない場合は出力をスキップ｡
'''

## 自身のAPIKEYを指定する｡以下の値はダミー
apikey = "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"

# 対象のアカウントIDを指定する｡以下の値はダミー
account_id = "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"

# 作成者情報を付加する対象のリソース使用量csvファイル名を指定する｡以下の値はダミー
usage_csv = "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx-instances-2023-02.csv"

'''
IBM Cloud APIのaccess URL, ヘッダの定義
'''
# アクセストークンの生成
generate_token_url = "https://iam.cloud.ibm.com/identity/token"
generate_token_headers = {
    "Content-Type": "application/x-www-form-urlencoded",
    "Accept": "application/json"
}

# アクセスグループリストの取得
get_accessgroups_url = "https://iam.cloud.ibm.com/v2/groups?account_id="

# アクセスグループのメンバーリストの取得
get_members_url_prefix = "https://iam.cloud.ibm.com/v2/groups/"
get_members_url_suffix = "/members?verbose=true&limit=100"

# サービスIDの取得
get_serviceids_url_prefix = "https://iam.cloud.ibm.com/v1/serviceids?account_id="
get_serviceids_url_suffix = "&pagesize=100"

# リソースリストの取得
get_resources_url = "https://resource-controller.cloud.ibm.com"

# 各リソースに対するタグの取得
get_tags_url = "https://tags.global-search-tagging.cloud.ibm.com/v3/tags?attached_to="


'''
処理開始
'''
# アクセストークンを生成し､以降のAPI実行で共通で利用するヘッダを生成する
generate_token_data = {
    "grant_type": "urn:ibm:params:oauth:grant-type:apikey",
    "apikey": f"{apikey}"
}

response = requests.post(
    generate_token_url, headers=generate_token_headers, data=generate_token_data)
response_json = response.json()
access_token = response_json["access_token"]

common_headers = {
    "Authorization": f"Bearer {access_token}",
    "Accept": "application/json"
}

# アカウントIDに対するアクセスグループのリストを取得する
response = requests.get(get_accessgroups_url +
                        account_id, headers=common_headers)
response_json = response.json()
groups = response_json["groups"]

# 各アクセスグループのメンバーリストを取得する
access_group_id = ""
member_list = {} # 作成者ID(IBMid)をキーにメールアドレスを保持する

for item in groups:
    access_group_id = item["id"]
    get_members_url = get_members_url_prefix + \
        access_group_id + get_members_url_suffix
    response = requests.get(get_members_url, headers=common_headers)
    response_json = response.json()
    members = response_json["members"]
    
    for item in members:
        member_list[item["iam_id"]] = item["email"]

# サービスIDのリストから､サービス名と説明の一覧を取得する
next = get_serviceids_url_prefix+account_id+get_serviceids_url_suffix
serviceid_list = {} # サービスID(IBMid)をキーにサービス名､サービス説明を保持する
# API応答内のnextが空でない限り繰り返す
while True:
    response = requests.get(next, headers=common_headers)
    response_json = response.json()

    next = ""
    if "next" in response_json:
        next = response_json["next"]
    
    serviceids = response_json["serviceids"]

    for item in serviceids:

        name = item["name"]  # サービス名

        description = ""  # サービス説明
        if "description" in item:
            description = item["description"]

        serviceid_list[item["iam_id"]] = (name, description)

    if next == "":
        break



# リソースリストの取得
next_url = "/v2/resource_instances" # next_urlの初期値
resource_list = [["crn", "name", "service_name1", "service_name2", 
                  "catalog_name", "created_at", "created_by", "email", "workspace_created_by", "tags", "service_name", "service_description"]] # csv出力時ヘッダ

# API応答内のnext_urlが空でない限り繰り返す
while True:
    response = requests.get(get_resources_url+next_url, headers=common_headers)
    response_json = response.json()

    next_url = response_json["next_url"]

    resources = response_json["resources"]

    # csv出力対象項目に関する情報を取得する
    for item in resources:
        crn = item["crn"]  # インスタンスID
        service_name1 = crn.split(':')[4] # crnからサービス名に関わる文字列を取得
        service_name2 = crn.split(':')[8] # crnからサービス名に関わる文字列を取得
        name = item["name"]  # リソース名
        created_by = item["created_by"]  # 作成者のサービスIDまたはIBMid
        created_at = item["created_at"]  # 作成時刻
        
        email = ""  # IBMidに対するemailアドレス
        if created_by in member_list:
            email = member_list[created_by]

        catalog_name = ""  # 拡張パラメータ内のリソース種別情報
        try:
            catalog_name = item["extensions"]["workspace"]["catalog_name"]
        except KeyError:
            pass

        workspace_created_by = ""  # 拡張パラメータ内の作成者情報
        try:
            workspace_created_by = item["extensions"]["workspace"]["created_by"]
        except KeyError:
            pass

        service_name = ""
        service_description = ""
        if created_by in serviceid_list:
            service_name,service_description = serviceid_list[created_by]

        # crnをキーにタグを取得する
        tags = ""
        response = requests.get(get_tags_url + crn, headers=common_headers)
        response_json = response.json()

        items = response_json["items"]
        if items is not None:
            tags = items

        # リソースリストに出力情報を追加する
        resource_list.append([crn, name, service_name1, service_name2, 
                             catalog_name, created_at, created_by, email, workspace_created_by, tags, service_name, service_description])

    if next_url is None:
        break


# リソースリストをcsvファイルへ出力
now = datetime.now()
timestamp = now.strftime("%Y%m%d_%H%M%S")
filename = "resource_list_" + timestamp + ".csv"

with open(filename, 'w', newline='') as f:
    writer = csv.writer(f, delimiter=',')
    writer.writerows(resource_list)


# 読み込み対象のリソース使用量csvファイルが存在する場合は作成者情報を追加する
if os.path.isfile(usage_csv):
    # crnをキーに作成者ID(IBMid)､メールアドレス､タグ情報を保持する
    crn_to_creator = {}
    for item in resource_list:
        crn_to_creator[item[0]] = (item[6], item[7], item[9])

    # 読み込んだファイルに作成者ID(IBMid)､メールアドレス､タグ情報の列を追加する
    data = []
    with open(usage_csv, 'r', newline='') as f:
        reader = csv.reader(f)
        index = 0
        for row in reader:
            # アカウント情報に関する1-3行目は無視する
            if index == 3:
                row.append("created_by")
                row.append("email")
                row.append("workspace_created_by")
            
            # 5行目以降に列を追加
            elif index > 3:
                if len(row) != 1:  # 最終行"--this is the end of report--"は処理対象外
                    crn = row[3]
                    if crn in crn_to_creator:
                        created_by, email, workspace_created_by = crn_to_creator[crn]
                        row.append(created_by)
                        row.append(email)
                        row.append(workspace_created_by)
            data.append(row)
            index += 1

    # 使用量ファイルの出力
    now = datetime.now()
    timestamp = now.strftime("%Y%m%d_%H%M%S")
    filename = "usage_list_" + timestamp + ".csv"

    with open(filename, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerows(data)
