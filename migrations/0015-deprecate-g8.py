#!/usr/bin/env python
from mist.api.models import Machine, Network, Volume


def remove_g8_clouds():
    try:
        from mist.api.clouds.models import GigG8Cloud
    except ImportError:
        return

    failed = updated = 0
    clouds = GigG8Cloud.objects()
    total = len(clouds)
    if not total:
        return
    print(f'Removing {total} G8 clouds')

    for cloud in clouds:
        try:
            Machine.objects(cloud=cloud).delete()
            Network.objects(cloud=cloud).delete()
            Volume.objects(cloud=cloud).delete()
            cloud.delete()
            updated += 1
            print('OK')
        except Exception as e:
            failed += 1
            print('Delete cloud %s (%s) failed: %r' % (
                cloud.id, cloud.name, e))

    print(f'{updated} clouds deleted succesfully')
    print(f'{failed} clouds failed')


if __name__ == '__main__':
    remove_g8_clouds()
