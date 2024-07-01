# get_device_id

**`pyglaze.device.get_device_id`**

::: pyglaze.device.get_device_id

**`pyglaze.device.list_devices`**

::: pyglaze.device.list_devices

## Examples


#### Find a device
First, we list all devices

```py
from pyglaze.device import list_devices

print(list_devices())
```
```
['glaze1', 'glaze2', 'carmen']
```

Now, we can get our desired device ID
```py
from pyglaze.device import get_device_id

print(get_device_id("carmen"))
```
```
6a54db26-fa88-4146-b04f-b84b945bfea8
```
