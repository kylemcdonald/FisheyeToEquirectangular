import numpy as np
import cv2

class FisheyeToEquirectangular:
    def __init__(self, n=2048, side=3072, blending=16, aperture=1):
        self.blending = blending
        blending_ratio = blending / n
        x_samples = np.linspace(0-blending_ratio, 1+blending_ratio, n+blending*2)
        y_samples = np.linspace(-1, 1, n)

        # equirectangular
        x, y = np.meshgrid(x_samples, y_samples)

        # longitude/latitude
        longitude = x * np.pi
        latitude = y * np.pi / 2

        # 3d vector
        Px = np.cos(latitude) * np.cos(longitude)
        Py = np.cos(latitude) * np.sin(longitude)
        Pz = np.sin(latitude)

        # 2d fisheye
        aperture *= np.pi
        r = 2 * np.arctan2(np.sqrt(Px*Px + Pz*Pz), Py) / aperture
        theta = np.arctan2(Pz, Px)
        theta += np.pi
        x = r * np.cos(theta)
        y = r * np.sin(theta)

        x = np.clip(x, -1, 1)
        y = np.clip(y, -1, 1)

        x = (-x + 1) * side / 2
        y = (y + 1) * side / 2

        self.x = x.astype(np.float32)
        self.y = y.astype(np.float32)
    
    def unwarp_single(self, img, interpolation=cv2.INTER_LINEAR, border=cv2.BORDER_REFLECT):
        return cv2.remap(
            img, self.x, self.y,
            interpolation=interpolation,
            borderMode=border
        )
    
    def unwarp_pair(self, left, right, **kwargs):
        ul = self.unwarp_single(left, **kwargs)
        ur = self.unwarp_single(right, **kwargs)
        b = self.blending

        la = ul[:,:b]
        lb = ul[:,b:b*2]
        lc = ul[:,b*2:-b*2]
        ld = ul[:,-b*2:]

        ra = ur[:,:b*2]
        rb = ur[:,b*2:-b*2]
        rc = ur[:,-b*2:-b]
        rd = ur[:,-b:]

        fd = np.linspace(1, 0, b*2).reshape(1,-1,1).repeat(3, axis=2)
        fu = np.linspace(0, 1, b*2).reshape(1,-1,1).repeat(3, axis=2)
        
        out = np.hstack((
            lb * fu[:,b:] + rd * fd[:,b:],
            lc,
            ld * fd + ra * fu,
            rb,
            rc * fd[:,:b] + la * fu[:,:b] 
        ))
        
        return out