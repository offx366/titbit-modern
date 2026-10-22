// Exercise calls across the actual engine's translation-unit boundary.
#include "../src/native/geometry_interfaces.h"
extern "C" int probe_geometry() {
    ObservedFrustumInterface frustum;
    ObservedVector3 origin(0, 0, 10), direction(0, 0, -2), normal(0, 0, 1);
    if (frustum.RayPlane(origin, direction, normal, 0) != 5.0f) return 1;
    ObservedVector3 parallel(1, 0, 0);
    if (frustum.RayPlane(origin, parallel, normal, 0) != -1.0f) return 2;
    ObservedVector3 below(0, 0, -10);
    if (frustum.RayPlane(below, direction, normal, 0) != -5.0f) return 3;
    return 0;
}
