# Run through the pinned CE Rails runtime, with its private operator volume mounted.
# Output is a private file; tokens and passwords are never printed.
require 'json'
input_path = ENV.fetch('CHATWOOT_BOOTSTRAP_INPUT', '/operator/bootstrap-input.json')
output_path = ENV.fetch('CHATWOOT_BOOTSTRAP_OUTPUT', '/operator/bootstrap-result.json')
raise 'Keep the existing commissioning receipt.' if File.exist?(output_path)
input = JSON.parse(File.read(input_path))
raise 'Use a fresh, customer-isolated Chatwoot database.' if Account.exists?
result = nil
ActiveRecord::Base.transaction do
  user = User.new(email: input.fetch('operator_email'), name: 'Company communication operator',
                  password: input.fetch('operator_password'), password_confirmation: input.fetch('operator_password'))
  user.skip_confirmation!
  user.save!
  account = Account.create!(name: input.fetch('name'), locale: 'bg')
  AccountUser.create!(account: account, user: user, role: :administrator)
  api_channel = Channel::Api.create!(account: account, hmac_mandatory: true)
  api_inbox = Inbox.create!(account: account, channel: api_channel, name: 'Company service',
                           greeting_enabled: false, enable_auto_assignment: false, lock_to_single_conversation: true)
  InboxMember.create!(inbox: api_inbox, user: user)
  email_inbox = nil
  if input['email'].to_s != ''
    email_channel = Channel::Email.create!(account: account, email: input.fetch('email'),
                                           imap_enabled: false, smtp_enabled: false)
    email_inbox = Inbox.create!(account: account, channel: email_channel, name: 'Customer email',
                               greeting_enabled: false, enable_auto_assignment: false)
    InboxMember.create!(inbox: email_inbox, user: user)
  end
  webhook = Webhook.create!(account: account, name: 'Rocoto communication receipts',
                            url: input.fetch('callback_url'), subscriptions: %w[message_created message_updated])
  token = user.access_token || user.create_access_token!
  result = { schema_version: 1, company_id: input.fetch('company_id'), environment_id: input.fetch('environment_id'),
             origin: input.fetch('origin'), account_id: account.id, api_token: token.token,
             webhook_secret: webhook.secret, service_inbox_id: api_inbox.id, email_inbox_id: email_inbox&.id || 0,
             webhook_id: webhook.id, operator_user_id: user.id }
end
File.open(output_path, File::WRONLY | File::CREAT | File::EXCL, 0600) { |file| file.write(JSON.pretty_generate(result)) }
puts 'Created the customer account and private commissioning receipt.'
