"""Small hosted-login routes; the caller retains the native session middleware."""
import json

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse

from access import COOKIE, LEGACY_COOKIE
from workspace_auth import AuthError, FLOW_COOKIE, ProviderUnavailable, STATE_TTL


def register_workspace_auth(app, auth, *, public_origin, session_details, set_session):
    """Callbacks: session_details(session)->dict; set_session(response,token,request)."""
    def token(request):
        return request.cookies.get(COOKIE) or request.cookies.get(LEGACY_COOKIE)

    def failed(code):
        response = RedirectResponse('/?auth_error=' + code, status_code=303)
        response.headers['Cache-Control'] = 'no-store'
        response.delete_cookie(FLOW_COOKIE, path='/auth')
        return response

    @app.get('/api/auth/config')
    async def auth_config():
        return JSONResponse(auth.public_config(), headers={'Cache-Control': 'no-store'})

    @app.get('/auth/login')
    async def login(request: Request):
        try:
            result = await auth.begin(workspace=request.query_params.get('workspace') or None,
                return_to=request.query_params.get('return_to', '/'),
                invitation_token=request.query_params.get('invitation_token') or None)
        except AuthError as error:
            return failed(error.code)
        response = RedirectResponse(result['url'], status_code=303)
        response.headers['Cache-Control'] = 'no-store'
        response.set_cookie(FLOW_COOKIE, result['browser_nonce'], max_age=STATE_TTL,
                            secure=public_origin.startswith('https://'), httponly=True, samesite='lax', path='/auth')
        return response

    @app.get('/auth/callback')
    async def callback(request: Request):
        try:
            result = await auth.complete(code=request.query_params.get('code'),
                state=request.query_params.get('state'), browser_nonce=request.cookies.get(FLOW_COOKIE))
        except AuthError as error:
            return failed(error.code)
        response = RedirectResponse(result['return_to'], status_code=303)
        response.headers['Cache-Control'] = 'no-store'
        response.delete_cookie(FLOW_COOKIE, path='/auth')
        set_session(response, result['token'], request)
        return response

    @app.get('/api/workspaces')
    async def workspaces(request: Request):
        try:
            session = await auth.validate_session(token(request), force=True)
            return JSONResponse(auth.workspaces(session), headers={'Cache-Control': 'private, no-store'})
        except ProviderUnavailable:
            raise HTTPException(503, 'Workspace access is reconnecting. Try again.') from None
        except AuthError:
            raise HTTPException(401, 'Sign in to open your workspaces.') from None

    @app.get('/api/workspaces/access')
    async def workspace_access(request: Request):
        try:
            session = await auth.validate_session(token(request), force=True)
            if not session:
                raise AuthError('sign_in_required')
            environment = session['environment']['id']
            enabled = auth.enabled and environment in auth.config.organizations
            can_manage = not session.get('viewing_as') and (
                session.get('role') == 'owner' or session.get('workspace_admin') is True)
            return JSONResponse({'environment_id': environment, 'hosted_login': enabled,
                'can_invite': bool(enabled and can_manage)},
                headers={'Cache-Control': 'private, no-store'})
        except ProviderUnavailable:
            raise HTTPException(503, 'Workspace access is reconnecting. Try again.') from None
        except AuthError:
            raise HTTPException(401, 'Sign in to open your workspace.') from None

    async def body(request):
        try:
            raw = bytearray()
            async for chunk in request.stream():
                raw.extend(chunk)
                if len(raw) > 4096:
                    raise ValueError()
            result = json.loads(raw)
            if not isinstance(result, dict):
                raise ValueError()
            return result
        except (ValueError, TypeError):
            raise HTTPException(400, 'Provide workspace details.') from None

    @app.post('/api/workspaces/select')
    async def select(request: Request):
        data = await body(request)
        if set(data) != {'environment_id'}:
            raise HTTPException(400, 'Choose a workspace.')
        try:
            session = await auth.select(token(request), data['environment_id'])
            return JSONResponse(session_details(session), headers={'Cache-Control': 'private, no-store'})
        except ProviderUnavailable:
            raise HTTPException(503, 'Workspace access is reconnecting. Try again.') from None
        except (AuthError, ValueError):
            raise HTTPException(403, 'Choose one of your workspaces.') from None

    @app.post('/api/workspaces/invitations')
    async def invite(request: Request):
        data = await body(request)
        if set(data) != {'environment_id', 'email'}:
            raise HTTPException(400, 'Provide a workspace and email address.')
        try:
            result = await auth.invite(token(request), data['environment_id'], data['email'])
            return JSONResponse(result, headers={'Cache-Control': 'private, no-store'})
        except ProviderUnavailable:
            raise HTTPException(503, 'Invitations are reconnecting. Try again.') from None
        except AuthError:
            raise HTTPException(403, 'Use workspace owner access to invite a member.') from None
