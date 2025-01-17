from mist.api.auth.methods import auth_context_from_request
from mist.api.models import Cloud
from mist.api.exceptions import NotFoundError
from mist.api.helpers import view_config, params_from_request
from mist.api.containers import methods


@view_config(route_name='api_v1_cloud_clusters',
             request_method='GET', renderer='json')
def list_cloud_clusters(request):
    """
    Tags: clusters
    ---
    Lists clusters on cloud along with their metadata.
    Check Permissions takes place in filter_list_clusters.
    READ permission required on cloud.
    READ permission required on cluster.
    ---
    cloud:
      in: path
      required: true
      type: string
    """
    auth_context = auth_context_from_request(request)
    cloud_id = request.matchdict['cloud']
    params = params_from_request(request)
    cached = bool(params.get('cached', False))

    # SEC get filtered resources based on auth_context
    try:
        Cloud.objects.get(owner=auth_context.owner,
                          id=cloud_id, deleted=None)
    except Cloud.DoesNotExist:
        raise NotFoundError('Cloud does not exist')
    clusters = methods.filter_list_clusters(auth_context, cloud_id,
                                            cached=cached)
    return clusters
