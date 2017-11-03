L.LatLngBounds.prototype.union = function(bounds) {
    var east = this.getEast() > bounds.getEast() ? this.getEast() : bounds.getEast()
    var west = this.getWest() < bounds.getWest() ? this.getWest() : bounds.getWest()
    var north = this.getNorth() > bounds.getNorth() ? this.getNorth() : bounds.getNorth()
    var south = this.getSouth() < bounds.getSouth() ? this.getSouth() : bounds.getSouth()

    return L.latLngBounds([south, west],[north,east])
}
