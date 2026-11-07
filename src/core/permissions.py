CONTENT = {'content:read','content:write'}
OPERATIONS = {'operations:read','operations:write'}
ADMIN = CONTENT | OPERATIONS | {'settings:read','settings:write','banking:write'}
ROLES = {
    'super_admin': ADMIN | {'users:manage','logs:read'},
    'admin': ADMIN,
    'manager': CONTENT | OPERATIONS | {'settings:read'},
    'editor': CONTENT,
    'reviewer': OPERATIONS,
}
