from .views import TEAM_META, TEAM_ORDER, _allowed_teams_for_user, _can_access_preparo, _can_view_members_index, _commercial_allowed


def sidebar_context(request):
    allowed_teams = _allowed_teams_for_user(request.user)
    sidebar_team_links = [
        {
            'slug': slug,
            'title': TEAM_META[slug]['title'],
            'url_name': slug,
        }
        for slug in TEAM_ORDER
        if slug in allowed_teams
    ]
    return {
        'sidebar_team_links': sidebar_team_links,
        'can_view_members_index': _can_view_members_index(request.user),
        'can_view_preparo': _can_access_preparo(request.user),
        'can_view_commerce': _commercial_allowed(request.user),
    }