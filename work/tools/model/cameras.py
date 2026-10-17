"""Photo cameras in MakeHuman units (dm, Y up, front +Z).

The photo was taken close (MediaPipe puts the face ~86 cm from the lens), so the body uses a
pinhole camera: things nearer the lens (crossed forearms) appear larger than the shoulders or belt.
Focal length comes from the head fit (pixels per decimeter at the face's distance)."""
import math

import numpy as np
from scipy.optimize import least_squares


class Perspective:
    def __init__(self, f, cam, roll, center):
        self.f, self.cam, self.roll, self.center = float(f), np.asarray(cam, float), float(roll), np.asarray(center, float)

    def project(self, X):
        X = np.atleast_2d(X)
        rel = X - self.cam
        depth = -rel[:, 2]
        c, s = math.cos(self.roll), math.sin(self.roll)
        xr = c * rel[:, 0] - s * rel[:, 1]
        yr = s * rel[:, 0] + c * rel[:, 1]
        return np.stack([self.center[0] + self.f * xr / depth, self.center[1] - self.f * yr / depth], 1)

    def unproject(self, px, z):
        depth = self.cam[2] - z
        xr = (px[0] - self.center[0]) * depth / self.f
        yr = -(px[1] - self.center[1]) * depth / self.f
        c, s = math.cos(-self.roll), math.sin(-self.roll)
        return np.array([self.cam[0] + c * xr - s * yr, self.cam[1] + s * xr + c * yr, z])

    def view_dir(self, X):
        """Unit vectors from points toward the camera."""
        d = self.cam - np.atleast_2d(X)
        return d / np.linalg.norm(d, axis=1, keepdims=True)

    def to_json(self):
        return {'f': self.f, 'cam': self.cam.tolist(), 'roll': self.roll, 'center': self.center.tolist()}

    @classmethod
    def from_json(cls, d):
        return cls(d['f'], d['cam'], d['roll'], d['center'])


def fit_body(model_pts, photo_pts, weights, s_head, face_z, face_dist, image_size):
    """Camera position (x, y) and roll that best map model points onto photo points; the
    distance and focal length are fixed from the face (s_head px/dm at face_dist dm)."""
    center = np.array(image_size, float) / 2
    f = s_head * face_dist
    cz = face_z + face_dist
    model_pts, photo_pts, w = map(np.asarray, (model_pts, photo_pts, weights))

    def resid(p):
        cam = Perspective(f, (p[0], p[1], cz), p[2], center)
        return ((cam.project(model_pts) - photo_pts) * np.sqrt(w)[:, None]).ravel()

    x0 = np.r_[model_pts[:, 0].mean(), model_pts[:, 1].mean(), 0.0]
    r = least_squares(resid, x0)
    cam = Perspective(f, (r.x[0], r.x[1], cz), r.x[2], center)
    err = np.linalg.norm(cam.project(model_pts) - photo_pts, axis=1)
    return cam, err
