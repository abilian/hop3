#!/bin/bash
# Rocket.Chat start script for Hop3

set -eu -o pipefail

CODE_DIR="${HOP3_CODE_DIR:-/app/code}"
DATA_DIR="${HOP3_DATA_DIR:-/app/data}"
HOP3_USER="${HOP3_USER:-www-data}"

echo "=> Creating runtime directories"
mkdir -p /run/rocket.chat/{babel-cache,ufs,deno-cache} /run/root.mongodb/mongosh

# Setup babel cache symlink
ln -sf /run/rocket.chat/babel-cache /home/${HOP3_USER}/.babel-cache 2>/dev/null || true

# MongoDB CLI
mongo_cli="mongosh --quiet ${MONGODB_HOST:-localhost}:${MONGODB_PORT:-27017}/${MONGODB_DATABASE:-rocketchat} -u ${MONGODB_USERNAME:-rocketchat} -p ${MONGODB_PASSWORD:-}"

[[ -f "${DATA_DIR}/env" ]] && mv "${DATA_DIR}/env" "${DATA_DIR}/env.sh"

if [[ ! -f "${DATA_DIR}/env.sh" ]]; then
    echo "=> First run setup"
    echo -e "# Add custom env configuration in this file\n\n# export CREATE_TOKENS_FOR_USERS=true\n" > "${DATA_DIR}/env.sh"
    ${mongo_cli} --eval "db.rocketchat_settings.updateOne({ _id: \"Accounts_TwoFactorAuthentication_By_Email_Auto_Opt_In\" }, { \$set: { value: false }}, { upsert: true })"
fi

if [[ -n "${OIDC_ISSUER:-}" ]]; then
    echo "Setting up OIDC"
    provider_name=$(php -r "echo addslashes(\"${OIDC_PROVIDER_NAME:-SSO}\");")
    ${mongo_cli} --eval "db.rocketchat_settings.updateOne({ _id: 'Accounts_OAuth_Custom-Hop3'}, { \$set: { group: 'OAuth', section: 'Custom OAuth: Hop3', value: true, autocomplete: true, blocked: false, enterprise: false, env: false, hidden: false, i18nDescription: 'Accounts_OAuth_Custom-Hop3_Description', i18nLabel: 'Accounts_OAuth_Custom_Enable', packageValue: false, persistent: true, public: false, requiredOnWizard: false, secret: false, sorter: 30, type: 'boolean', valueSource: 'packageValue' }}, { upsert: true })"
    ${mongo_cli} --eval "db.rocketchat_settings.updateOne({ _id: 'Accounts_OAuth_Custom-Hop3-url'}, { \$set: { value: '${OIDC_ISSUER}', group: 'OAuth', section: 'Custom OAuth: Hop3', 'autocomplete':true,'blocked':false, 'enterprise':false,'env':false,'hidden':false,'i18nDescription':'Accounts_OAuth_Custom-Hop3-url_Description','i18nLabel':'URL','packageValue':'','persistent':true,'public':false,'requiredOnWizard':false,'secret':false,'sorter':1, 'type':'string','valueSource':'packageValue' }}, { upsert: true })"
    ${mongo_cli} --eval "db.rocketchat_settings.updateOne({ _id: 'Accounts_OAuth_Custom-Hop3-id'}, { \$set: { value: '${OIDC_CLIENT_ID}', group: 'OAuth', section: 'Custom OAuth: Hop3', 'autocomplete':true,'blocked':false,'enterprise':false,'env':false,'hidden':false,'i18nDescription':'Accounts_OAuth_Custom-Hop3-id_Description','i18nLabel':'Accounts_OAuth_Custom_id','packageValue':'','persistent':true,'public':false,'requiredOnWizard':false,'secret':false,'sorter':9, 'type':'string','valueSource':'packageValue' }}, { upsert: true })"
    ${mongo_cli} --eval "db.rocketchat_settings.updateOne({ _id: 'Accounts_OAuth_Custom-Hop3-secret'}, { \$set: { value: '${OIDC_CLIENT_SECRET}', group: 'OAuth', section: 'Custom OAuth: Hop3', 'autocomplete':true,'blocked':false, 'enterprise':false,'env':false,'hidden':false,'i18nDescription':'Accounts_OAuth_Custom-Hop3-secret_Description','i18nLabel':'Accounts_OAuth_Custom_Secret','packageValue':'','persistent':true,'public':false,'requiredOnWizard':false,'secret':false,'sorter':10, 'type':'string','valueSource':'packageValue' }}, { upsert: true })"
    ${mongo_cli} --eval "db.rocketchat_settings.updateOne({ _id: 'Accounts_OAuth_Custom-Hop3-token_path'}, { \$set: { value: '/token', group: 'OAuth', section: 'Custom OAuth: Hop3', 'autocomplete':true,'blocked':false,'enterprise':false,'env':false,'hidden':false,'i18nDescription':'Accounts_OAuth_Custom-Hop3-token_path_Description','i18nLabel':'Accounts_OAuth_Custom_Token_Path','packageValue':'/oauth/token','persistent':true,'public':false,'requiredOnWizard':false,'secret':false,'sorter':2,'type':'string','valueSource':'packageValue' }}, { upsert: true })"
    ${mongo_cli} --eval "db.rocketchat_settings.updateOne({ _id: 'Accounts_OAuth_Custom-Hop3-authorize_path'}, { \$set: { value: '/auth', group: 'OAuth', section: 'Custom OAuth: Hop3', 'autocomplete':true,'blocked':false,'enterprise':false,'env':false,'hidden':false,'i18nDescription':'Accounts_OAuth_Custom-Hop3-authorize_path_Description','i18nLabel':'Accounts_OAuth_Custom_Authorize_Path','packageValue':'/oauth/authorize','persistent':true,'public':false,'requiredOnWizard':false,'secret':false,'sorter':6,'type':'string','valueSource':'packageValue' }}, { upsert: true })"
    ${mongo_cli} --eval "db.rocketchat_settings.updateOne({ _id: 'Accounts_OAuth_Custom-Hop3-scope'}, { \$set: { value: 'openid email profile', group: 'OAuth', section: 'Custom OAuth: Hop3', 'autocomplete':true,'blocked':false,'enterprise':false,'env':false,'hidden':false,'i18nDescription':'Accounts_OAuth_Custom-Hop3-scope_Description','i18nLabel':'Accounts_OAuth_Custom_Scope','packageValue':'openid','persistent':true,'public':false,'requiredOnWizard':false,'secret':false,'sorter':7,'type':'string','valueSource':'packageValue' }}, { upsert: true })"
    ${mongo_cli} --eval "db.rocketchat_settings.updateOne({ _id: 'Accounts_OAuth_Custom-Hop3-identity_path'}, { \$set: { value: '/me', group: 'OAuth', section: 'Custom OAuth: Hop3', 'autocomplete':true,'blocked':false,'enterprise':false,'env':false,'hidden':false,'i18nDescription':'Accounts_OAuth_Custom-Hop3-identity_path_Description','i18nLabel':'Accounts_OAuth_Custom_Identity_Path','packageValue':'/me','persistent':true,'public':false,'requiredOnWizard':false,'secret':false,'sorter':5,'type':'string','valueSource':'packageValue' }}, { upsert: true })"
    ${mongo_cli} --eval "db.rocketchat_settings.updateOne({ _id: 'Accounts_OAuth_Custom-Hop3-username_field'}, { \$set: { value: 'sub', group: 'OAuth', section: 'Custom OAuth: Hop3', 'autocomplete':true,'blocked':false,'enterprise':false,'env':false,'hidden':false,'i18nDescription':'Accounts_OAuth_Custom-Hop3-username_field_Description','i18nLabel':'Accounts_OAuth_Custom_Username_Field','packageValue':'','persistent':true,'public':false,'requiredOnWizard':false,'secret':false,'sorter':16,'type':'string','valueSource':'packageValue' }}, { upsert: true })"
    ${mongo_cli} --eval "db.rocketchat_settings.updateOne({ _id: 'Accounts_OAuth_Custom-Hop3-email_field'}, { \$set: { value: 'email', group: 'OAuth', section: 'Custom OAuth: Hop3', 'autocomplete':true,'blocked':false,'enterprise':false,'env':false,'hidden':false,'i18nDescription':'Accounts_OAuth_Custom-Hop3-email_field_Description','i18nLabel':'Accounts_OAuth_Custom_Email_Field','packageValue':'','persistent':true,'public':false,'requiredOnWizard':false,'secret':false,'sorter':17,'type':'string','valueSource':'packageValue' }}, { upsert: true })"
    ${mongo_cli} --eval "db.rocketchat_settings.updateOne({ _id: 'Accounts_OAuth_Custom-Hop3-name_field'}, { \$set: { value: 'name', group: 'OAuth', section: 'Custom OAuth: Hop3', 'autocomplete':true,'blocked':false,'enterprise':false,'env':false,'hidden':false,'i18nDescription':'Accounts_OAuth_Custom-Hop3-name_field_Description','i18nLabel':'Accounts_OAuth_Custom_Name_Field','packageValue':'','persistent':true,'public':false,'requiredOnWizard':false,'secret':false,'sorter':18,'type':'string','valueSource':'packageValue' }}, { upsert: true })"
    ${mongo_cli} --eval "db.rocketchat_settings.updateOne({ _id: 'Accounts_OAuth_Custom-Hop3-login_style'}, { \$set: { value: 'redirect', group: 'OAuth', section: 'Custom OAuth: Hop3', 'autocomplete':true,'blocked':false,'enterprise':false,'env':false,'hidden':false,'i18nDescription':'Accounts_OAuth_Custom-Hop3-login_style_Description','i18nLabel':'Accounts_OAuth_Custom_Login_Style','packageValue':'popup','persistent':true,'public':false,'requiredOnWizard':false,'secret':false,'sorter':11,'type':'select','valueSource':'packageValue','values':[{'key':'redirect','i18nLabel':'Redirect'},{'key':'popup','i18nLabel':'Popup'},{'key':'','i18nLabel':'Default'}] }}, { upsert: true })"
    ${mongo_cli} --eval "db.rocketchat_settings.updateOne({ _id: 'Accounts_OAuth_Custom-Hop3-button_label_text'}, { \$set: { value: 'Login with ${provider_name}', group: 'OAuth', section: 'Custom OAuth: Hop3', 'autocomplete':true,'blocked':false,'enterprise':false,'env':false,'hidden':false,'i18nDescription':'Accounts_OAuth_Custom-Hop3-button_label_text_Description','i18nLabel':'Accounts_OAuth_Custom_Button_Label_Text','packageValue':'','persistent':true,'public':false,'requiredOnWizard':false,'secret':false,'sorter':12,'type':'string','valueSource':'packageValue' }}, { upsert: true })"
    ${mongo_cli} --eval "db.rocketchat_settings.updateOne({ _id: 'Accounts_OAuth_Custom-Hop3-button_color'}, { \$set: { value: '#1d74f5', group: 'OAuth', section: 'Custom OAuth: Hop3', 'autocomplete':true,'blocked':false,'enterprise':false,'env':false,'hidden':false,'i18nDescription':'Accounts_OAuth_Custom-Hop3-button_color_Description','i18nLabel':'Accounts_OAuth_Custom_Button_Color','packageValue':'#1d74f5','persistent':true,'public':false,'requiredOnWizard':false,'secret':false,'sorter':14,'type':'string','valueSource':'packageValue' }}, { upsert: true })"
    ${mongo_cli} --eval "db.rocketchat_settings.updateOne({ _id: 'Accounts_OAuth_Custom-Hop3-show_button'}, { \$set: { value: true, group: 'OAuth', section: 'Custom OAuth: Hop3', 'autocomplete':true,'blocked':false,'enterprise':false,'env':false,'hidden':false,'i18nDescription':'Accounts_OAuth_Custom-Hop3-show_button_Description','i18nLabel':'Accounts_OAuth_Custom_Show_Button_On_Login_Page','packageValue':true,'persistent':true,'public':false,'requiredOnWizard':false,'secret':false,'sorter':28,'type':'boolean','valueSource':'packageValue' }}, { upsert: true })"
    ${mongo_cli} --eval "db.rocketchat_settings.updateOne({ _id: 'Accounts_OAuth_Custom-Hop3-token_sent_via'}, { \$set: { value: 'payload', group: 'OAuth', section: 'Custom OAuth: Hop3', 'autocomplete':true,'blocked':false,'enterprise':false,'env':false,'hidden':false,'i18nDescription':'Accounts_OAuth_Custom-Hop3-token_sent_via_Description','i18nLabel':'Accounts_OAuth_Custom_Token_Sent_Via','packageValue':'payload','persistent':true,'public':false,'requiredOnWizard':false,'secret':false,'sorter':3,'type':'select','valueSource':'packageValue','values':[{'key':'header','i18nLabel':'Header'},{'key':'payload','i18nLabel':'Payload'}] }}, { upsert: true })"
    ${mongo_cli} --eval "db.rocketchat_settings.updateOne({ _id: 'Accounts_OAuth_Custom-Hop3-identity_token_sent_via'}, { \$set: { value: 'header', group: 'OAuth', section: 'Custom OAuth: Hop3', 'autocomplete':true,'blocked':false,'enterprise':false,'env':false,'hidden':false,'i18nDescription':'Accounts_OAuth_Custom-Hop3-identity_token_sent_via_Description','i18nLabel':'Accounts_OAuth_Custom_Identity_Token_Sent_Via','packageValue':'default','persistent':true,'public':false,'requiredOnWizard':false,'secret':false,'sorter':4,'type':'select','valueSource':'packageValue','values':[{'key':'default','i18nLabel':'Same_As_Token_Sent_Via'},{'key':'header','i18nLabel':'Header'},{'key':'payload','i18nLabel':'Payload'}] }}, { upsert: true })"
    ${mongo_cli} --eval "db.rocketchat_settings.updateOne({ _id: 'Accounts_OAuth_Custom-Hop3-access_token_param'}, { \$set: { value: 'access_token', group: 'OAuth', section: 'Custom OAuth: Hop3', 'autocomplete':true,'blocked':false,'enterprise':false,'env':false,'hidden':false,'i18nDescription':'Accounts_OAuth_Custom-Hop3-access_token_param_Description','i18nLabel':'Accounts_OAuth_Custom_Access_Token_Param','packageValue':'access_token','persistent':true,'public':false,'requiredOnWizard':false,'secret':false,'sorter':8,'type':'string','valueSource':'packageValue' }}, { upsert: true })"
    ${mongo_cli} --eval "db.rocketchat_settings.updateOne({ _id: 'Accounts_OAuth_Custom-Hop3-key_field'}, { \$set: { value: 'username', group: 'OAuth', section: 'Custom OAuth: Hop3', 'autocomplete':true,'blocked':false,'enterprise':false,'env':false,'hidden':false,'i18nDescription':'Accounts_OAuth_Custom-Hop3-key_field_Description','i18nLabel':'Accounts_OAuth_Custom_Key_Field','packageValue':'username','persistent':true,'public':false,'requiredOnWizard':false,'secret':false,'sorter':15,'type':'select','valueSource':'packageValue','values':[{'key':'username','i18nLabel':'Username'},{'key':'email','i18nLabel':'Email'}] }}, { upsert: true })"
fi

# Settings
echo "=> Update site url"
${mongo_cli} --eval "db.rocketchat_settings.updateOne({ _id: \"Site_Url\" }, { \$set: { value: \"${HOP3_APP_ORIGIN:-http://localhost:3000}\" }}, { upsert: true })"

# Email
echo "=> Setting up email"
${mongo_cli} --eval "db.rocketchat_settings.updateOne({ _id: \"SMTP_Host\" }, { \$set: { value: \"${SMTP_HOST:-localhost}\" }}, { upsert: true })"
${mongo_cli} --eval "db.rocketchat_settings.updateOne({ _id: \"SMTP_Port\" }, { \$set: { value: \"${SMTP_PORT:-25}\" }}, { upsert: true })"
${mongo_cli} --eval "db.rocketchat_settings.updateOne({ _id: \"SMTP_Username\" }, { \$set: { value: \"${SMTP_USERNAME:-}\" }}, { upsert: true })"
${mongo_cli} --eval "db.rocketchat_settings.updateOne({ _id: \"SMTP_Password\" }, { \$set: { value: \"${SMTP_PASSWORD:-}\" }}, { upsert: true })"

# From email
if [[ -n "${MAIL_FROM_DISPLAY_NAME:-}" ]]; then
    export from_email="${MAIL_FROM_DISPLAY_NAME} <${MAIL_FROM:-noreply@localhost}>"
else
    export from_email="${MAIL_FROM:-noreply@localhost}"
fi
${mongo_cli} --eval "db.rocketchat_settings.updateOne({ _id: \"From_Email\" }, { \$set: { value: process.env.from_email }}, { upsert: true })"

# TURN
if [[ -n "${STUN_SERVER:-}" ]]; then
    ${mongo_cli} --eval "db.rocketchat_settings.updateOne({ _id: \"WebRTC_Servers\" }, { \$set: { value: \"stun:${STUN_SERVER}:${STUN_PORT:-3478}, :${TURN_SECRET:-}@turn:${TURN_SERVER:-}:${TURN_PORT:-3478}\" }}, { upsert: true })"
fi

# Disable the update checker
${mongo_cli} --eval "db.rocketchat_settings.updateOne({ _id: \"Update_EnableChecker\" }, { \$set: { value: false }}, { upsert: true })"

chown -R ${HOP3_USER}:${HOP3_USER} "${DATA_DIR}" /run/rocket.chat

source "${DATA_DIR}/env.sh"

export ROOT_URL="${HOP3_APP_ORIGIN:-http://localhost:3000}"
export MONGO_URL="${MONGODB_URL:-mongodb://${MONGODB_USERNAME:-rocketchat}:${MONGODB_PASSWORD:-}@${MONGODB_HOST:-localhost}:${MONGODB_PORT:-27017}/${MONGODB_DATABASE:-rocketchat}}"
export MONGO_OPLOG_URL="${MONGODB_OPLOG_URL:-}"
export PORT=3000
export DENO_DIR=/run/rocket.chat/deno-cache

# Until we update mongodb
export SKIP_MONGODEPRECATION_CHECK="true"

echo "=> Starting Rocket.Chat"
exec su -s /bin/bash ${HOP3_USER} -c "cd ${CODE_DIR} && node ${CODE_DIR}/bundle/main.js"
