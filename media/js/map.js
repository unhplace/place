//MAYBE
//layer adjustment

//TableViewDelegate
//functions
//    numberOfSections() -> int
//    numberOfRowsInSection(section) -> int
//    cellForRowInSection(row,section) -> Cell
//    hoverStartedForRowInSection(row, section) -> nothing
//    hoverEndedForRowInSection(row, section) -> nothing
//    selectedCellForRowInSection(row, section) -> nothing
//    headerForSection(section) -> SectionHeader (null for no header)
//    footerForSection(section) -> SectionFooter (null for no footer)
//    sectionSortable(section) -> bool
//    orderingForSection(section) -> int (1 asc, -1 desc)
//    orderChangedForSection(section) -> nothing
//
//GenericCellDelegate (?)
//functions
//    onAdd() -> nothing (called after the cell is added to the table)
//
//ColorPickerDelegate
//function
//    selectedColor(color) -> nothing (as [r,g,b,a])
//
//LocationDelegate
//functions
//    locationFound(latlng, accuracy)
//    locationError(error)
//TimeSliderDelegate
//functions
//    enableTimeSlider()
//    disableTimeSlider()
//    numberOfTimeSliderItems()
//    itemForTimeSliderPosition(position)
//    setTimeSliderPosition(position)
//    yearsForTimeSlider()
//OGPDelegate
//attributes
//    proxyURL - the address of the OGP proxy server 
//    itemProperties - an array of item properties to download and store
//
//SearchDelegate
//attributes
//    searchOptions - a dictionary of values to use when searching
//functions
//    searchRequested() -> nothing
//
//MapViewDelegate
//functions
//    mapViewMoveEnded() -> nothing
//    mapViewClicked(latlng) -> nothing
//
//PaginatingCellDelegate
//functions
//    paginatingCellSetPageForSection(page,section) -> nothing
//
//DownloadFooterDelegate
//functions
//    downloadRequested(email_address) -> nothing
//    clearLayers() -> nothing
//
//CollapsingSectionHeaderDelegate
//functions
//    collapseStateForSection(section) -> bool (true: collapsed)
//    collapseStateChangedForSection(section, collapsed) -> nothing
//GazetteerMenuDelegate
//    gazetteerPolygonSelected(polygonID, type, name) -> nothing
//    gazetteerPolygonUnSelected() -> nothing
//CategoryChangeDelegate
//    selectedCategoryForIndex(index) -> nothing

//Search Options Dictionary Key Constants
SO_KEYWORD_TEXT = "keywordText"
SO_LIMIT_TO_LOCATION = "limitToLocation"
SO_LOCATION_TEXT = "locationText"
SO_SHOW_POLYGON = "showPolygon"
SO_ORIGINATOR_TEXT = "originatorText"
SO_DATATYPE_TEXT = "datatypeText"

SO_START_YEAR = "startYear"
SO_END_YEAR = "endYear"

//OSM Response Key Constants
OSM_BBOX = "boundingbox"
OSM_DISPLAY_NAME = "display_name"
OSM_GEOJSON = "geojson"
OSM_ID = "osm_id"

//specific sections
SECTION_SELECTED = 0
SECTION_LOADING = 1

//Other constants
ENTER_KEY_CODE = 13
HTTP_OK = 200
XHR_DONE = 4

function OGPController(map_id, map_options, proxyURL, institutionID) { 
    this.proxyURL = proxyURL
    this.institutionID = institutionID
    this.solrFieldString = "ContentDate,DataType,Institution,LayerDisplayName,LayerId,Location,Name,MinX,MaxX,MinY,MaxY,Originator,WorkspaceName" //also exposed as itemProperties

    this.nominatimURL = "/nominatim"

    this.loadingItems = false
    this.currentRequest = null

    this.searchOptions = {}
    this.searchData = {}

    this.openSection = 1

    this.selectedGazetteerPolygon = null

    this.selectedItems = []
    this.internalItems = {}
    this.internalItemTotals = {}
    this.timeSliderItems = []

    this.mapView = new MapView(map_id, map_options, this)
    this.searchView = new SearchView("searchview", "search-field", ["location", "keyword", "showpolygon", "startyear", "endyear", "originator", "datatype"], this)
    this.gazetteerMenu = new GazetteerMenu("search-button-gazetteer", "/gazetteer", this)

    this.selectedItemsTableView = new TableView("selected-items-tableview") 
    this.selectedItemsDelegate = new SelectedItemsDelegate(this.selectedItems, this.selectedItemsTableView, this.mapView, this)
    this.selectedItemsTableView.delegate = this.selectedItemsDelegate

    this.internalItemsTableView = new TableView("internal-items-tableview")
    this.internalItemsDelegate = new InternalItemsDelegate(this.internalItems, this.internalItemsTableView, this.mapView, this)
    this.internalItemsTableView.delegate = this.internalItemsDelegate

    this.categoryOptions = ["Collection", "Category", "Data Type", "All Items"]
    this.categoryIndex = 0
    this.categoryChangeTableView = new TableView("category-change-tableview")
    this.categoryChangeDelegate = new CategoryChangeTableViewDelegate(this.categoryOptions, this)
    this.categoryChangeTableView.delegate = this.categoryChangeDelegate

    this.tableViews = new TableViewCollection([
        this.selectedItemsTableView, 
        this.internalItemsTableView,
        this.categoryChangeTableView
    ])

    this.mapView.timeSliderButton = new TimeSliderButton({delegate: this})
    this.mapView.map.addControl(this.mapView.timeSliderButton)
    
    this.mapView.showNHButton = new ShowNHButton({"mapView": this.mapView})
    this.mapView.map.addControl(this.mapView.showNHButton)

    this.gazetteerLayers = new L.LayerGroup()
    this.enteredLocationLayers = new L.LayerGroup()

    this.mapView.map.addLayer(this.gazetteerLayers)
    this.mapView.map.addLayer(this.enteredLocationLayers)

    //modify the default leaflet vector styles
    this.setDefaultLeafletStyle()

//  //menu dialog set up plus general dialog parameters

    var dialogSetup = function(url, title, extraDialogClass, extraSetup) {
        $.ajax(url).done(function(data) {
            var element = $(data)
            var settings = { 
                title: title,
                position: { my: "top", at: "top+100px", of: window },
                buttons: [{
                    text: "Close",
                    click: function() { 
                        $(this).dialog("close") 
                    }
                }]
            }
            if (extraDialogClass) { settings.dialogClass = extraDialogClass}
            var dialog = $(element).dialog(settings)
            if (extraSetup) { extraSetup() }
        })
    }

    var controller = this
    $("#contact-button").click(function() {
        dialogSetup("/contact.html", "Contact Info")
    })

    $("#help-button").click(function(e) {
        dialogSetup("/help.html", "Help")
    })

    $("#about-button").click(function() {
        dialogSetup("/welcome.html", "Welcome to the UNH PLACE Geoportal", "ui-dialog-wide-dialog")
    })

    if (location.search.includes("layers=")) {
        this.loadEnteredLayers()
    }
    else {
//      dialogSetup("/welcome.html", "Welcome to the UNH PLACE Geoportal", "ui-dialog-wide-dialog", function() {
//          controller.loadDataForMapBounds()
//      })
        controller.setSearchViewPlaceholder()
        controller.loadDataForMapBounds()
    }
}

Object.defineProperty(OGPController.prototype, "groupNames", {
    get: function() {
        return Object.keys(this.internalItems)
    }
})

Object.defineProperty(OGPController.prototype, "itemProperties", {
    get: function() {
        return this.solrFieldString.split(",")
    }
})

Object.defineProperty(OGPController.prototype, "lastInternalSection", {
    //because "selected items" is section 0, this section number ends up being the same as the number of collections
    get: function() { return this.groupNames.length }
})

Object.defineProperty(OGPController.prototype, "urlWithLayers", {
    get: function() {
        var layersParameter = sprintf("layers=%s", this.selectedItems.map(function(i) { return i.LayerId}))
        var url = sprintf("%s?%s", location.href.replace(/\?.*/,""), layersParameter)
        return url
    }
})

Object.defineProperty(OGPController.prototype, "noResultsFound", {
    get: function() {
        return Object.keys(this.internalItems).length == 0
    }
})

OGPController.prototype.setDefaultLeafletStyle = function() {
    var vectorStyle = {
        color: "rgb(0,102,255)",
        fillOpacity: 0.2,
        opacity: 1,
        weight: 1
    }

    L.GeoJSON.prototype.options = {}
    L.GeoJSON.mergeOptions(vectorStyle)
    DeferredGeoJSON.prototype.options = {}
    DeferredGeoJSON.mergeOptions(vectorStyle)
    L.Rectangle.mergeOptions(vectorStyle)
    ClickPassingGeoJSON.mergeOptions(vectorStyle)
    AntimeridianAdjustedGeoJSON.mergeOptions(vectorStyle)
}

OGPController.prototype.loadEnteredLayers = function() {
    var layers = this.getURLParameter("layers").split(",")
    var controller = this

    var internalPromise = null
    if (layers.length > 0) {
        internalPromise = new Promise(function(resolve, reject) {
            $.ajax(sprintf("/ogp/items?layers=%s&return=%s", layers, controller.solrFieldString)).done(function(data) {
                resolve(data.response)
            })
        })
    }
    else {
        internalPromise = Promise.resolve()
    }

    this.loadingItems = true
    this.tableViews.reloadData()
    Promise.all([internalPromise]).then(function(results) {
        var internalItems = results[0] || []
        for (var i = internalItems.length - 1; i >= 0; --i) {
            var item = internalItems[i]
            var boundedItem = new BoundedItem(item, item.collection)
            boundedItem.selected = true
            controller.mapView.visibleLayers.addLayer(boundedItem.mapLayer)
            controller.selectedItems.push(boundedItem)
        }

        if (controller.selectedItems.length > 1) { controller.selectedItems.reverse() }

        controller.mapView.map.fitBounds(controller.getBBoxForItems(controller.selectedItems))
    })
}

OGPController.prototype.loadInternalItemsForMapBounds = function(groupID) {
    var bbox = this.mapView.map.getBounds().toBBoxString()
    var keyword = this.searchOptions[SO_KEYWORD_TEXT]
    var originator = this.searchOptions[SO_ORIGINATOR_TEXT]
    var startYear = this.searchOptions[SO_START_YEAR] || ""
    var endYear = this.searchOptions[SO_END_YEAR]
    var datatype = this.searchOptions[SO_DATATYPE_TEXT]

    //the search end year needs to be increased by one to be inclusive of the entered end year
    //since there might be no value entered, end year is first checked for existence
    endYear = parseInt(endYear) ? endYear + 1 : ""

    var groupType = this.categoryOptions[this.categoryIndex].replace(" ", "").toLowerCase()
    var url = sprintf("/ogp/find?grouped=%s&return=%s", groupType, this.solrFieldString)

    if (this.searchData[OSM_ID] && this.searchOptions[SO_LIMIT_TO_LOCATION]) {
        url += sprintf("&osm_id=%s", this.searchData[OSM_ID])
    }
    else if (this.selectedGazetteerPolygon && this.searchOptions[SO_LIMIT_TO_LOCATION]) {
        url += sprintf("&polygon=%s:%s", this.selectedGazetteerPolygon.type, this.selectedGazetteerPolygon.id)
    }
    else {
        url += sprintf("&bbox=%s", bbox)
    }

    if (startYear || endYear) {
        var yearRange = sprintf("%s-%s", startYear, endYear)
        url = sprintf("%s&years=%s", url, yearRange)
    }
    if (keyword) {
        url = sprintf("%s&keyword=%s", url, keyword)
    }
    if (originator) {
        url = sprintf("%s&originator=%s", url, originator)
    }
    if (datatype) {
        url = sprintf("%s&datatype=%s", url, datatype)
    }


    var number = 20

//  if (groupType == "allitems") {
//      if (!this.allItemsNumber) {
//          var tvs_h = Number($("#tableviews").css("height").replace("px", ""))
//          var sit_h = Number($("#selected-items-tableview").css("height").replace("px",""))
//          var cct_h = Number($("#category-change-tableview").css("height").replace("px", ""))
//      
//          var iit_h = (tvs_h - sit_h - cct_h) - 48 //get height of header and page control programatically
//          this.allItemsNumber = Math.floor(iit_h/20) - 1
//      }
//      number = this.allItemsNumber
//  }

    var pageNumber = this.internalItemsDelegate.sectionCurrentPages[groupID] || 1
    var start = (pageNumber - 1) * number
    var end = (pageNumber) * number
    url += sprintf("&start=%d&end=%d", start, end)

    if (groupID) {
        url += sprintf("&id=%s", groupID)
    }

    var controller = this
    var promise = new Promise(function(resolve, reject) {
        $.ajax(url).done(function(response) { resolve(response) })
    })
    promise.then(function(data) {
        if (!groupID) {
            Object.replace(controller.internalItems, {})
            Object.replace(controller.internalItemTotals, {})
            Object.replace(controller.internalItemsDelegate.sectionCurrentPages, {})
        }

        var groups = data.response.groups
        var selectedItemNames = controller.selectedItems.map(function(i) { return i.Name })

        for (var i = 0; i < groups.length; ++i) {
            var group = groups[i]
            controller.internalItemTotals[group.name] = group.totalNumber
            controller.internalItems[group.name] = group.items.map(function(i) { 
                var itemIndex = selectedItemNames.indexOf(i.Name)
                if (itemIndex == -1) {
                    return new BoundedItem(i, group.name) 
                }
                else {
                    return controller.selectedItems[itemIndex]
                }
            })
            controller.internalItems[group.name].removeNulls()
        }

        controller.loadingItems = false
        controller.currentRequest = null
    }).then(null, function(error) { throw error })

    return promise
}

OGPController.prototype.loadDataForMapBounds = function(groupID, section) {
    var controller = this
    if (!groupID) {
        controller.loadingItems = true
        controller.tableViews.reloadData()
    }

    var internalItemsPromise = this.loadInternalItemsForMapBounds(groupID, section)

    return Promise.all([internalItemsPromise]).then(function() {
        controller.loadingItems = false
        controller.searchView.enableSearch()

        if (section) {
            controller.internalItemsTableView.reloadSection(section)
        }
        else {
            controller.tableViews.reloadData()
        }
    })
}

OGPController.prototype.loadOSMPolygon = function(location_string) {
    location_string = location_string.replace(/\s/g, "+")
    var polygonURL = sprintf("%s/search?q=%s&format=json&polygon_geojson=1", this.nominatimURL, location_string)

    var controller = this

    var promise = new Promise(function(resolve, reject) {
        $.ajax(polygonURL).done(function(data) { resolve(data) })
    })

    promise.then(function(data) {
        var polygon = data[0][OSM_GEOJSON]
        var layer = new ClickPassingGeoJSON(polygon, {
            "mapViewDelegate": controller
        })
        controller.gazetteerLayers.clearLayers()
        controller.enteredLocationLayers.clearLayers()
        controller.enteredLocationLayers.addLayer(layer)
    })

    return promise
}

OGPController.prototype.loadGazetteerPolygon = function(polygonID, type) {
    var map = this.mapView.map
    var controller = this

    var id = sprintf("%s:%s", type, polygonID)
    var polygonObject = (id == "state:02" || id == "county:02016" ? AntimeridianAdjustedGeoJSON : ClickPassingGeoJSON)

    var promise = new Promise(function(resolve, reject) {

        $.ajax(sprintf("/gazetteer/%s?id=%s", type, polygonID)).done(function(data) {
            resolve(data)
        })
    })

    promise.then(function(data) {
        var l = new polygonObject(data, {"mapViewDelegate": controller})
        controller.selectedGazetteerPolygon["bounds"] = l.getBounds().toBBoxString()
        controller.enteredLocationLayers.clearLayers()
        controller.gazetteerLayers.clearLayers()
        controller.gazetteerLayers.addLayer(l)

        var oldBounds = controller.mapView.map.getBounds()
        controller.mapView.map.fitBounds(l.getBounds())
        var newBounds = controller.mapView.map.getBounds()
        if (oldBounds.equals(newBounds)) {
            controller.loadDataForMapBounds()
        }
    })

    return promise
}

OGPController.prototype.getBBoxForItems = function(items) {
    if (items && items.length > 0) {
        var bounds = items[0].bounds

        for (var i = 1; i < items.length; ++i) {
            bounds = bounds.union(items[i].bounds)
        }
        
        return bounds
    }
}

OGPController.prototype.setSearchViewPlaceholder = function() {
    if (this.searchOptions[SO_LIMIT_TO_LOCATION] && this.selectedGazetteerPolygon) {
        this.searchView.placeholderText = sprintf("Enter a location (Showing Gazetteer Entry: %s)", this.selectedGazetteerPolygon.name)
    }
    else {
        var center = this.mapView.map.getCenter()
        var mapZoom = this.mapView.map.getZoom()
        var osmSearchURL = sprintf("%s/reverse?format=json&lat=%f&lon=%f&zoom=%d",
            this.nominatimURL, center.lat, center.lng, mapZoom > 13 ? 13 : mapZoom)
    
        var nominatimPromise = new Promise(function(resolve, reject) {
            $.ajax(osmSearchURL).done(function(response) {
                resolve(response)
            })
        })
    
        var searchView = this.searchView
        nominatimPromise.then(function(data) {
            var displayName = data.display_name
            searchView.placeholderLocation = displayName
        })
    }
}

//MISC UTILITY
OGPController.prototype.getURLParameter = function(parameter) {
    if (!location.search.includes(parameter)) {
        return null
    }

    var queryString = location.search
    var r = new RegExp(sprintf("%s=.*?($|&)", parameter))
    var value = r.exec(queryString)[0].replace(sprintf("%s=", parameter),"").replace("&","")

    return value
}

function SelectedItemsDelegate(selectedItems, tableView, mapView, controller) {
    this.selectedItems = selectedItems
    this.tableView = tableView
    this.mapView = mapView
    this.controller = controller
    this.proxyURL = controller.proxyURL
}

_sid = SelectedItemsDelegate.prototype

_sid.itemForRowInSection = function(row, section) {
    if (row > this.selectedItems.length) {
        return null
    }
    else {
        return this.selectedItems[row]
    }
}

_sid.numberOfSections = function() {
    return 1
}

_sid.numberOfRowsInSection = function(section) {
    return this.selectedItems.length || 1
}

_sid.cellForRowInSection = function(row, section) {
    if (this.selectedItems.length == 0) {
        return new NoSelectedItemsCell()
    }
    else {
        var item = this.selectedItems[row]
        var delegate = this
        var allowSelection = !this.controller.timeSliderEnabled
        return new BoundedItemCell(item, row, section, delegate, delegate, allowSelection, this.mapView)
    }
}

_sid.headerForSection = function(section) {
    var headerText = "Selected Items"
    var subheaderText = sprintf("<span class='drag-help'>Click and drag %s to order layers</span>", "<img src='/media/img/sort_handle.png'>")
    return new SectionHeader(headerText, subheaderText, section)
}

_sid.footerForSection = function(section) {
    if (this.selectedItems.length > 0) {
        return new DownloadFooter(this.controller)
    }
    else {
        return null
    }
}

_sid.hoverStartedForRowInSection = function(row, section) {
    var item = this.selectedItems[row]
    this.mapView.previewLayers.addLayer(item.previewOutline)
}

_sid.hoverEndedForRowInSection = function(row, section) {
    this.mapView.previewLayers.clearLayers()
}

_sid.sectionSortable = function(section) {
    return true
}

_sid.orderingForSection = function(section) {
    return -1
}
_sid.orderChangedForSection = function(section) {
    var sectionElementID = sprintf("#selected-items-tableview-section-%d", section)
    var sectionElement = $(sectionElementID)

    var rows = sectionElement.children(".tableview-row")
    var newSelectedItems = []

    var currentSelectedItems = this.selectedItems

    $(rows).each(function() {
        var rowNum = parseInt($(this).attr("data-row"))
        newSelectedItems.push(currentSelectedItems[rowNum])
    })
    newSelectedItems.reverse()
    this.selectedItems.replaceValues(newSelectedItems)
    this.tableView.reloadSection(section)

    $(this.selectedItems).each(function() {
        this.mapLayer.bringToFront()
    })
}

_sid.selectedCellForRowInSection = function(row, section) {
    var item = this.selectedItems[row]
    var controller = this.controller
    controller.mapView.previewLayers.removeLayer(item.previewOutline)

    if (item.selected) {
        item.selected = false

        controller.mapView.visibleLayers.removeLayer(item.mapLayer)

        controller.selectedItems.remove(this.selectedItems.indexOf(item))
        controller.tableViews.reloadData()
    }
}


function InternalItemsDelegate(internalItems, tableView, mapView, controller) {
    this.internalItems = internalItems
    this.tableView = tableView
    this.mapView = mapView
    this.controller = controller
    this.proxyURL = controller.proxyURL

    this.collapseStates = {}
    this.sectionCurrentPages = {}
}

_iid = InternalItemsDelegate.prototype

_iid.collectionKeyForSection = function(section) {
    return Object.keys(this.internalItems)[section]
}

_iid.collectionForSection = function(section) {
    var key = this.collectionKeyForSection(section)
    return this.internalItems[key]
}

_iid.collectionTotalForSection = function(section) {
    var key = this.collectionKeyForSection(section)
    return this.controller.internalItemTotals[key]
}

_iid.itemForRowInSection = function(row, section) {
    var index = row - 1

    return this.collectionForSection(section)[index]
}

_iid.numberOfSections = function() { 
    if (this.controller.loadingItems) {
        return 1
    }
    if (this.controller.noResultsFound) {
        return 1
    }

    return Object.keys(this.internalItems).length
}

_iid.numberOfRowsInSection = function(section) { 
    if (this.controller.loadingItems) {
        return 1
    }
    if (this.controller.noResultsFound) {
        return 1
    }

    var numberOfItems = this.collectionForSection(section).length

    return numberOfItems + 1
}

_iid.cellForRowInSection = function(row, section) { 
    if (this.controller.loadingItems) {
        return new LoadingCell()
    }
    if (this.controller.noResultsFound) {
        return new NoResultsCell()
    }

    if (row == 0) {
        var collection = this.collectionKeyForSection(section)
        var totalNumber = this.controller.internalItemTotals[collection]
        var numberPerPage = 20

//      var key = Object.keys(this.controller.internalItems)[section]
//      var numberPerPage = this.controller.internalItems[key].length

        var start = this.sectionCurrentPages[collection] || 1
        var pages = Math.ceil(totalNumber / numberPerPage)
        return new PaginatingCell(start, pages, section, this)
    }

    var item = this.itemForRowInSection(row, section)

    var delegate = this
    var allowSelection = true
    return new BoundedItemCell(item, row, section, delegate, delegate, allowSelection, this.mapView)
}

_iid.hoverStartedForRowInSection = function(row, section) {
    var item = this.itemForRowInSection(row, section)
    this.mapView.previewLayers.addLayer(item.previewOutline)
}

_iid.hoverEndedForRowInSection = function(row, section) {
    this.mapView.previewLayers.clearLayers()
}

_iid.selectedCellForRowInSection = function(row, section) {
    var controller = this.controller

    var item = this.itemForRowInSection(row, section)
    this.mapView.previewLayers.removeLayer(item.previewOutline)

    if (item.selected) {
        item.selected = false
        controller.mapView.visibleLayers.removeLayer(item.mapLayer)

        controller.selectedItems.remove(controller.selectedItems.indexOf(item))
        controller.tableViews.reloadData()
    }
    else {
        if (item.willDisableGeolocation && !controller.disabledGeolocation) {
            var dialogText = $(sprintf("<div><p class='dialog-text'>Due to security restrictions in Safari, displaying \"%s\" will disable the abilitiy to show your current location. You may also select this item for download without displaying it.</p></div>", item.LayerDisplayName))
            var disableElement = $("<div class='dialog-option'>Display and Disable Current Location</div>")
            var selectElement = $("<div class='dialog-option'>Select for Download Only</div>")
            var cancelElement = $("<div class='dialog-option'>Cancel Selection</div>")

            dialogText.prepend("<img src='/media/img/disable-location.png' class='disable-location-logo'>")

            disableElement.click(function() {
                controller.disabledGeolocation = true
                controller.mapView.locateButton.remove()

                item.selected = true
        
                controller.selectedItems.push(item)
                controller.tableViews.reloadData()

                controller.mapView.visibleLayers.addLayer(item.mapLayer)

                dialogText.dialog("close")
            })

            selectElement.click(function() {
                item.selected = true
        
                controller.selectedItems.push(item)
                controller.tableViews.reloadData()

                dialogText.dialog("close")
            })

            cancelElement.click(function() {
                $(dialogText).dialog("close")
            })

            dialogText.append(disableElement).append(selectElement).append(cancelElement)

            $(dialogText).dialog({
                dialogClass: "geolocation-dialog",
                modal: true,
                title: "Disable Showing Current Location?"
            })
        }
        else {
            item.selected = true
            controller.mapView.visibleLayers.addLayer(item.mapLayer)
    
            controller.selectedItems.push(item)
            controller.tableViews.reloadData()
        }
    }
}

_iid.headerForSection = function(section) { 
    if (this.controller.loadingItems) {
        return new SectionHeader("Loading Items In Map Bounds", null, section)
    }
    if (this.controller.noResultsFound) {
        return new SectionHeader("No Items Found", null, section)
    }

    var name = this.collectionKeyForSection(section)
    var itemNumber = this.collectionTotalForSection(section)
    var itemWord = itemNumber > 1 ? "items" : "item"
    var title = sprintf("%s (%d %s)", name, itemNumber, itemWord)

    return new CollapsingSectionHeader(title, section, this, "internal-items-tableview")
}

_iid.footerForSection = function(section) { 
    return null 
}

_iid.sectionSortable = function(section) { 
    return false 
}

_iid.orderingForSection = function(section) { 
    return 1 
}

_iid.orderChangedForSection = function(section) {
}

_iid.collapseStateForSection = function(section) {
    if (this.numberOfSections() == 1) {
        return false
    }

    var key = this.collectionKeyForSection(section)
    var state = this.collapseStates[key]
    if (state == undefined) {
        state = true
        this.collapseStates[key] = state
    }

    return state
}

_iid.collapseStateChangedForSection = function(section, state) {
    var key = this.collectionKeyForSection(section)
    this.collapseStates[key] = state
}

_iid.paginatingCellSetPageForSection = function(page, section) {
    var key = this.collectionKeyForSection(section)
    this.sectionCurrentPages[key] = page
    this.controller.loadDataForMapBounds(key, section)
}

function CategoryChangeTableViewDelegate(options, controller) {
    this.options = options
    this.controller = controller
    this.selectedIndex = 0
}

_cctvd = CategoryChangeTableViewDelegate.prototype

_cctvd.numberOfSections = function() { 
    if (this.controller.timeSliderBar && this.controller.timeSliderBar.visible) {
        return 0
    }
    else {
        return 1 
    }
}

_cctvd.numberOfRowsInSection = function(section) { 
    return 1 
}

_cctvd.cellForRowInSection = function(row, section) { 
    return new CategoryChangeCell(this.options, this.selectedIndex, this.controller, this)
}

_cctvd.hoverStartedForRowInSection = function(row, section) {
}

_cctvd.hoverEndedForRowInSection = function(row, section) {
}

_cctvd.selectedCellForRowInSection = function(row, section) {
}

_cctvd.headerForSection = function(section) { 
    return null 
}

_cctvd.footerForSection = function(section) { 
    return null 
}

_cctvd.sectionSortable = function(section) { 
    return false 
}

_cctvd.orderingForSection = function(section) { 
    return 1 
}

_cctvd.orderChangedForSection = function(section) {
}

function CategoryChangeCell(options, selectedIndex, delegate, tableViewDelegate) { 
    this.options = options
    this.selectedIndex = selectedIndex
    this.delegate = delegate
    this.tableViewDelegate = this
}

Object.defineProperty(CategoryChangeCell.prototype, "element", {
    get: function() {
        var cellElement = $("<div class='tableview-row no-highlight category-cell'></div>")
        for (var i = 0; i < this.options.length; ++i) {
            var option = this.options[i]
            var optionElement = $(sprintf("<span data-category-index='%d' class='category-option'>%s</span>", i, option))
            if (i == this.selectedIndex) {
                optionElement.addClass("selected")
            }

            var cell = this
            optionElement.click(function() {
                $(".category-option").removeClass("selected")
                $(this).addClass("selected")
                var index = Number($(this).attr("data-category-index"))
                cell.tableViewDelegate.selectedIndex = index
                cell.delegate.selectedCategoryForIndex(index)
            })

            $(cellElement).append(optionElement)
        }
        return cellElement
    }
})

function EmptyTableViewDelegate() {
}

_etvd = EmptyTableViewDelegate.prototype

_etvd.numberOfSections = function() { 
    return 0 
}

_etvd.numberOfRowsInSection = function(section) { 
    return 0 
}

_etvd.cellForRowInSection = function(row, section) { 
    return new TextCell("") 
}

_etvd.hoverStartedForRowInSection = function(row, section) {
}

_etvd.hoverEndedForRowInSection = function(row, section) {
}

_etvd.selectedCellForRowInSection = function(row, section) {
}

_etvd.headerForSection = function(section) { 
    return null 
}

_etvd.footerForSection = function(section) { 
    return null 
}

_etvd.sectionSortable = function(section) { 
    return false 
}

_etvd.orderingForSection = function(section) { 
    return 1 
}

_etvd.orderChangedForSection = function(section) {
}

//Search "delegate" methods
OGPController.prototype.searchRequested = function() {
    var map = this.mapView.map
    var controller = this
    this.searchView.disableSearch()
    
    var locationText = this.searchOptions[SO_LOCATION_TEXT]
    if (locationText) {
        this.selectedGazetteerPolygon = null
        var searchLocation = locationText.replace(/\s/g, "+")
        var osmSearchURL = sprintf("%s/search?q=%s&format=json", this.nominatimURL, searchLocation)
        var promise = new Promise(function(resolve, reject) {
            $.ajax(osmSearchURL).done(function(data) { resolve(data) })
        })

        promise.then(function(data) {
            if (data.length == 0) {
                alert(sprintf('Location "%s" not found.', locationText))
            }
            else if (data.length == 1) {
                controller.setLocation(data[0])
            }
            else {
                controller.showLocationSelection(data)
            }
        })
    }
    else {
        this.loadDataForMapBounds()
    }
}

OGPController.prototype.setLocation = function(osmData) {
    var bbox = osmData["boundingbox"]
    var minY = bbox[0]
    var maxY = bbox[1]
    var minX = bbox[2]
    var maxX = bbox[3]
    var bounds = L.latLngBounds([minY, minX], [maxY, maxX])

    if (this.searchOptions[SO_LIMIT_TO_LOCATION]) {
        this.searchData[OSM_ID] = osmData[OSM_ID]
        this.searchData[OSM_DISPLAY_NAME] = osmData[OSM_DISPLAY_NAME]
        this.searchData["bounds"] = bounds.toBBoxString()
    }


    if (this.searchOptions[SO_SHOW_POLYGON]) {
        this.loadOSMPolygon(osmData[OSM_DISPLAY_NAME])
    }


    if (false) {
    }
    else {
        var map = this.mapView.map
        var oldMapBounds = map.getBounds()
        map.fitBounds(bounds, {
            maxZoom: 15
        })
        var newMapBounds = map.getBounds()
        if (newMapBounds.equals(oldMapBounds)) { this.loadDataForMapBounds() }
    }
}

OGPController.prototype.showLocationSelection = function(osmResults) {
    var controller = this
    var dialogElement = $(sprintf("<div><h3><i>%d Locations Found</i></h3></div>", osmResults.length))

    var areaResults = osmResults.filter(function(osmResult) {
        var bbox = osmResult[OSM_BBOX]
        return bbox[0] != bbox[1]
    })
    areaResults.sort(function(a,b) { return a[OSM_DISPLAY_NAME] > b[OSM_DISPLAY_NAME] ? 1 : -1 })

    var pointResults = osmResults.filter(function(osmResult) {
        var bbox = osmResult[OSM_BBOX]
        return bbox[0] == bbox[1]
    })
    pointResults.sort(function(a,b) { return a[OSM_DISPLAY_NAME] > b[OSM_DISPLAY_NAME] ? 1 : -1 })

    var areaChoices = areaResults.map(function(osmResult) {
        var choice = $(sprintf("<div class='location-choice'>%s</div>", osmResult[OSM_DISPLAY_NAME]))
        $(choice).on("click", function() { 
            controller.setLocation(osmResult)
            $(dialogElement).dialog("close")
        })

        return choice
    })

    var pointChoices = pointResults.map(function(osmResult) {
        var choice = $(sprintf("<div class='location-choice'>%s</div>", osmResult[OSM_DISPLAY_NAME]))
        $(choice).on("click", function() { 
            controller.setLocation(osmResult)
            $(dialogElement).dialog("close")
        })

        return choice
    })

    if (areaChoices.length > 0) {
        dialogElement.append("<h3><img style='height: 18px' src='/media/img/location-area.png'>Areas</h3>")
        dialogElement.append(areaChoices)
    }
    if (pointChoices.length > 0) {
        dialogElement.append("<h3><img style='height: 18px' src='/media/img/location-point.png'>Single Locations</h3>")
        dialogElement.append(pointChoices)
    }

    var locationDialog = $(dialogElement).dialog({
        dialogClass: "ui-dialog-location-dialog",
        title: "Choose a Location", 
        buttons: [{
            text: "Close",
            click: function() {
                $(this).dialog("close")
                //reset
                controller.loadDataForMapBounds()
            }
        }]
    })
}


//MapView "delegate" methods
OGPController.prototype.mapViewMoveEnded = function() {
    this.setSearchViewPlaceholder()
    this.loadDataForMapBounds()

    var locationSearchField = $("#search-field-location")
    if (locationSearchField.val()) {
        locationSearchField.animate({
            "background-color": "#CCE5FF", 
            "color": "#CCE5FF"
        }, 100, "swing", function() {
            locationSearchField.val(locationSearchField.attr("placeholder"))
        }).animate(
        {
            "background-color": "#FFFFFF",
            "color": "#888888"
        }, 100, "swing", function() {
            locationSearchField.val("")
            locationSearchField.css("color", "black")
        })
    }
    var locationText = this.searchOptions[SO_LOCATION_TEXT]
    this.previousSearchOptions = {}
    this.previousSearchOptions[SO_LOCATION_TEXT] = locationText
    this.searchOptions[SO_LOCATION_TEXT] = null
}

if (location.search.indexOf("alert_point=true") > -1) {
    OGPController.prototype.mapViewClicked = function(latlng) {
        alert(sprintf("Lat, Lon: %f, %f", latlng.lat, latlng.lng))
    }
}

/*
OGPController.prototype.mapViewMouseMove = function(latlng) {
    
}
*/

//DownloadFooterDelegate functions

OGPController.prototype.downloadRequested = function(emailAddress, wfsFormat) {
    var downloadItems = []

    for (var i = 0; i < this.selectedItems.length; ++i) {
        var item = this.selectedItems[i]
        downloadItems.push(item.LayerId)
    }

    var url = sprintf("%s/download", this.proxyURL)

    var postData = {"email": emailAddress, "wfsFormat": wfsFormat}
    if (downloadItems.length > 0) {
        postData["layers"] = downloadItems.join()
    }

    $.ajax(url, {"method": "POST", "data": postData, "beforeSend": function(xhr, settings) {
        xhr.setRequestHeader("X-CSRFToken", Cookies.get("csrftoken"))
    }}).done(function(data) {
        alert(data.response)
    }).fail(function(request) {
        var errors = JSON.parse(request.responseText)["errors"]
        alert(sprintf("Unable to request download. [%s]", errors.join(", ")))
    })
}

OGPController.prototype.clearLayers = function() {
    for (var i = 0; i < this.selectedItems.length; ++i) {
        this.selectedItems[i].selected = false
    }

    this.mapView.visibleLayers.clearLayers()
    this.selectedItems.replaceValues([])
    this.tableViews.reloadData()
}

//LocationDelegate
OGPController.prototype.locationFound = function(latlng, accuracy) {
    var mapView = this.mapView
    var lat = latlng.lat
    var lng = latlng.lng

    mapView.map.removeLayer(mapView.userLocationLayer)
    mapView.userLocation = latlng

    mapView.userLocationMarker.setLatLng(latlng)
    mapView.userLocationMarker.bindPopup(sprintf("%.4f%s, %.4f%s", Math.abs(lat), lat > 0 ? "N" : "S", Math.abs(lng), lng > 0 ? "E" : "W"))
    mapView.userLocationAccuracyArea.setRadius(accuracy)
    mapView.userLocationAccuracyArea.setLatLng(latlng)

    mapView.map.addLayer(mapView.userLocationLayer)
    
    mapView.locateButton.options.spinner.stop()
    mapView.map.getZoom() > 15 ? mapView.map.setView(latlng, mapView.map.getZoom()) : mapView.map.setView(latlng, 15)
    
}

OGPController.prototype.locationError = function(error) {
}

//GazetteerMenuDelegate
OGPController.prototype.gazetteerPolygonSelected = function(polygonID, type, name) {
    var controller = this

    var map = this.mapView.map
    var id = sprintf("%s:%s", type, polygonID)
    this.selectedGazetteerPolygon = {"id": polygonID, "type": type, "name": name}
    this.gazetteerLayers.clearLayers()
    this.enteredLocationLayers.clearLayers()
    this.searchOptions[SO_LOCATION_TEXT] = null
    $("#search-field-location").val("")
    this.searchData = {}

    var polygonObject = id == "state:02" || id == "county:02016" ? AntimeridianAdjustedGeoJSON : ClickPassingGeoJSON

    if (this.searchOptions[SO_SHOW_POLYGON]) {
        this.loadGazetteerPolygon(polygonID, type)
    }
    else {
        $.ajax(sprintf("/gazetteer/bbox?id=%s", id)).done(function(data) {
            var l = new polygonObject(data)
            controller.selectedGazetteerPolygon["bounds"] = l.getBounds().toBBoxString()

            map.fitBounds(l.getBounds())
        })
    }
}

OGPController.prototype.gazetteerPolygonUnselected = function() {
    this.gazetteerLayers.clearLayers()
    this.previousGazetteerPolygon = this.selectedGazetteerPolygon
    this.selectedGazetteerPolygon = null
    this.gazetteerMenu.tableView.reloadData()
    this.loadDataForMapBounds()
}

//TimeSliderDelegate

OGPController.prototype.configureTimeSlider = function(e) {
    var controller = this

    var latlng = e.latlng
    controller.mapView.timeSliderButton.hideTooltip()
    controller.timeSliderPoint = latlng
    controller.timeSliderEnabled = true
    $("#mapview").removeClass("time-slider-selecting-point")

    var coord = sprintf("%f,%f", latlng.lng, latlng.lat)
    var url = sprintf("/ogp/items_at_coord?coord=%f,%f&fields=%s", latlng.lng, latlng.lat, this.solrFieldString)

    var itemsAtCoordPromise = new Promise(function(resolve, reject) {
        $.ajax(url).done(function(data) {
            resolve(data)
        })
    })

    itemsAtCoordPromise.then(function(result) {
        var items = result.response.map(function(item) {
            var foundItem = controller.selectedItems.find(function(i) { return i.LayerId == item.LayerId })
            return foundItem || new BoundedItem(item, item.collection)
        })

        controller.timeSliderItems = items

        controller.mapView.visibleLayers.clearLayers()

        controller.timeSliderBar = new TimeSliderBar(controller, controller.mapView)
        controller.mapView.map.addControl(controller.timeSliderBar.leafletControl)

        controller.internalItemsTableView.delegate = new TimeSliderTableViewDelegate(controller.mapView, controller.timeSliderItems, controller.timeSliderBar, controller, controller)
        controller.tableViews.reloadData()
    })
}

OGPController.prototype.enableTimeSlider = function() {
    var controller = this
    $("#mapview").addClass("time-slider-selecting-point")
    this.mapView.map.once("click", this.configureTimeSlider, this)
}

OGPController.prototype.disableTimeSlider = function() {
    this.mapView.map.off("click", this.configureTimeSlider, this)
    $("#mapview").removeClass("time-slider-selecting-point")

    this.mapView.visibleLayers.clearLayers()

    this.timeSliderPoint = null
    this.timeSliderEnabled = false
    this.timeSliderItems = []

    for (var i = 0; i < this.selectedItems.length; ++i) {
        var layer = this.selectedItems[i].mapLayer
        layer.setOpacity(1)
        this.mapView.visibleLayers.addLayer(layer)
    }

    $(this.selectedItems).each(function() {
        this.mapLayer.bringToFront()
    })
    
    if (this.timeSliderBar && this.timeSliderBar.visible) {
        this.mapView.map.removeControl(this.timeSliderBar.leafletControl) //will set visible to false
        this.internalItemsTableView.delegate = this.internalItemsDelegate
        this.tableViews.reloadData()
    }
}

OGPController.prototype.numberOfTimeSliderItems = function() {
    return this.timeSliderItems ? this.timeSliderItems.length : 0
}

OGPController.prototype.itemForTimeSliderPosition = function(position) {
    return this.timeSliderItems[position]
}

OGPController.prototype.setTimeSliderPosition = function(position){
    var item = this.itemForTimeSliderPosition(position)
    var layer = item.mapLayer

    this.mapView.visibleLayers.clearLayers()
    this.mapView.visibleLayers.addLayer(layer)

//  this.visibleLayers.eachLayer(function(l) { l.setOpacity(0) })
//  if (!this.visibleLayers.hasLayer(layer)) {
//      this.visibleLayers.addLayer(layer)
//  }
//  layer.bringToFront()
//  layer.setOpacity(1)
}

OGPController.prototype.yearsForTimeSlider = function() {
    var years = this.timeSliderItems.map(function(item) {
        return Number(item.ContentDate.substring(0,4))
    })
    return years
}

//CategoryChangeDelegate
OGPController.prototype.selectedCategoryForIndex = function(index) {
    if (index == this.categoryIndex) { return }

    this.categoryIndex = index
    this.categoryChangeDelegate.selectedIndex = index
    this.loadDataForMapBounds()
    $(".category-option").removeClass("selected")
    $(sprintf(".category-option[data-category-index='%d']", index)).addClass("selected")
}

//END OF DELEGATE SECTION


//TimeSliderTableViewDelegate
function TimeSliderTableViewDelegate(mapView, items, timeSliderBar, timeSliderDelegate, controller) {
    this.mapView = mapView
    this.items = items
    this.timeSliderBar = timeSliderBar
    this.timeSliderDelegate = timeSliderDelegate
    this.controller = controller
}

_tstvd = TimeSliderTableViewDelegate.prototype

_tstvd.numberOfSections = function() {
    return 1
}

_tstvd.numberOfRowsInSection = function(section) {
    return this.items.length
}

_tstvd.cellForRowInSection = function(row, section) {
    var item = this.items[row]
    var selected = this.timeSliderBar.currentPosition == row
    var cell = new TimeSliderTableViewCell(row, section, item, this, this.timeSliderBar, selected)

    return cell
}

_tstvd.hoverStartedForRowInSection = function(row, section) {
    var item = this.items[row]
    this.mapView.previewLayers.addLayer(item.previewOutline)
}

_tstvd.hoverEndedForRowInSection = function(row, section) {
    var item = this.items[row]
    this.mapView.previewLayers.clearLayers()
}

_tstvd.selectedCellForRowInSection = function(row, section) {
    var item = this.items[row]

    if (item.reloadSection) {
        item.reloadSection = false
        if (item.selected) {
            this.controller.selectedItems.push(item)
            this.controller.selectedItemsTableView.reloadSection(0)
        }
        else {
            var index = this.controller.selectedItems.indexOf(item)
            this.controller.selectedItems.remove(index)
            this.controller.selectedItemsTableView.reloadSection(0)
        }
    }
    else {
        this.timeSliderBar.currentPosition = row
    }
}

_tstvd.headerForSection = function(section) {
    var years = this.timeSliderDelegate.yearsForTimeSlider()
    var firstYear = years[0]
    var lastYear = years[years.length-1]
    return new SectionHeader(sprintf("Time Slider Items (%s to %s)", firstYear, lastYear), null, 1)
}

_tstvd.footerForSection = function(section) {
    return null
}

_tstvd.sectionSortable = function(section) {
    return false
}

_tstvd.orderingForSection = function(section) {
    return 1
}

function MapView(map_id, map_options, delegate) {
    map_options["attributionControl"] = false
    map_options["worldCopyJump"] = true
    map_options["maxZoom"] = 18

    this.delegate = delegate
    this.map = new L.Map(map_id, map_options)
    this.previewLayers = new L.LayerGroup()
    this.visibleLayers = new L.LayerGroup()
    this.map.addLayer(this.previewLayers)
    this.map.addLayer(this.visibleLayers)

    if (navigator.geolocation) {
        this.locateButton = new LocateButton({"mapView": this})
        this.map.addControl(this.locateButton)

        this.userLocation = null
        this.userLocationLayer = L.layerGroup()
        this.userLocationAccuracyArea = L.circle()
        this.userLocationAccuracyArea.setStyle({
            stroke: false
        })
        this.userLocationMarker = L.circleMarker(null, { 
            color: "#FFFFFF", fillColor: "#03f", opacity: 1, weight: 3, fillOpacity: 1, radius: 7
        })
        this.userLocationLayer.addLayer(this.userLocationAccuracyArea)
        this.userLocationLayer.addLayer(this.userLocationMarker)
    }

    if (L.Browser.retina) {
        this.base_layer = L.tileLayer('https://cartodb-basemaps-{s}.global.ssl.fastly.net/light_all/{z}/{x}/{y}@2x.png', {
            subdomains: ['a','b','c','d']
        })
    }
    else {
        this.base_layer = L.tileLayer('https://cartodb-basemaps-{s}.global.ssl.fastly.net/light_all/{z}/{x}/{y}.png', {
            subdomains: ['a','b','c','d']
        })
    }
    
    if (location.search.indexOf("base=false") == -1) {
        this.map.addLayer(this.base_layer)
    }

    var attribution = new L.Control.Attribution({ position: "topright" })
    attribution.addAttribution('&copy; UNH, &copy; <a href="http://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors, &copy; <a href="http://cartodb.com/attributions">CartoDB</a>')
    this.map.addControl(attribution)

    if (delegate.mapViewClicked) {
        this.map.on("click", function(e) {
            delegate.mapViewClicked(e.latlng)
        })
    }

    if (delegate.mapViewMoveEnded) {
        this.map.on("moveend", function() {
            delegate.mapViewMoveEnded()
        })
    }

    if (delegate.locationFound) {
        this.map.on("locationfound", function(e) {
            var latlng = L.latLng(e.latitude, e.longitude)
            delegate.locationFound(latlng, e.accuracy)
        })
    }

    var locateButton = this.locateButton
    this.map.on("locationerror", function(e) {
        locateButton.enabled = false
        $(locateButton.element).removeClass("enabled")
        locateButton.options.spinner.stop()

        if (e.code == 2) { //user allowed geolocation, but service is disabled
            alert("Unable to get your location.")
        }
        else if (e.code == 1) { //user denied geolocation
            alert("Please enable location services if you would like to display your location.")
            this.removeControl(locateButton.leafletControl)
        }
        else {
            delegate.locationError(e)
        }
    })
}

MapView.prototype.removeUserLocation = function() {
    this.userLocation = null
    this.map.removeLayer(this.userLocationLayer)
}

var ShowNHButton = L.Control.extend({
    options: {
        bounds: L.latLngBounds([42.6970417, -72.5571232], [45.3057789, -70.5613592]),
        mapView: null,
        position: "topleft"
    },
    initialize: function(options) {
        options = L.Util.setOptions(this, options)
        return options
    },
    onAdd: function(map) {
        var buttonElement = this._createButtonElement()
        L.DomEvent.disableClickPropagation(buttonElement)
        return buttonElement
    },
    _createButtonElement: function() {
        var element = $("<div class='leaflet-button' id='show-nh-button' title='Show NH'><img src='/media/img/nh-button.png'></div>")[0]

        var button = this
        $(element).click(function() {
            button.options.mapView.map.fitBounds(button.options.bounds)
        })
        return element
    }
})

var LocateButton = L.Control.extend({
    options: {
        enabled: false,
        mapView: null,
        position: "topleft",
        spinner: new Spinner({scale: 0.5})
    },
    initialize: function(options) {
        options = L.Util.setOptions(this, options)
        return options
    },
    onAdd: function(map) {
        var buttonElement = this._createButtonElement()
        L.DomEvent.disableClickPropagation(buttonElement)
        return buttonElement
    },
    _createButtonElement: function() {
        var element = $("<div class='leaflet-button' id='locate-button' title='Current Location'><img src='/media/img/locate-button.png'></div>")[0]
        var button = this
        $(element).click(function() { 
            if (!button.options.enabled) {
                button.enableButton()
            }
            else {
                button.disableButton()
            }
        })
        this.buttonElement = element
        return $(element)[0]
    },
    disableButton: function() {
        this.options.enabled = false
        $(this.buttonElement).removeClass("enabled")
        this.options.mapView.removeUserLocation()
    },
    enableButton: function() {
        this.options.enabled = true
        $(this.buttonElement).addClass("enabled")
        this.options.spinner.spin(this.buttonElement)

        this.options.mapView.map.locate()
    }
})

function Tooltip(bodyText, direction) {
    this.bodyElement = $(sprintf("<div class='tooltip-body'>%s</div>", bodyText.replace(/ /g,"&nbsp;")))
    this.direction = "left" //would use direction (top, right, bottom, left)
    this._element = null
}

Object.defineProperty(Tooltip.prototype, "element", {
    get: function() {
        if (!this._element) {
            this._element = $(sprintf("<div class='tooltip'><div class='%s-arrow'></div></div>", this.direction))
            this._element.append($(this.bodyElement))
        }

        return this._element
    }
})

var TimeSliderButton = L.Control.extend({
    options: {
        delegate: null,
        enabled: false,
        position: "topleft",
        tooltip: new Tooltip("Click a point on the map to start")
    },
    initialize: function(options) {
        options = L.Util.setOptions(this, options)
        return options
    },
    onAdd: function(map) {
        var buttonElement = this._createButtonElement()
        //using L.DomEvent.disableClickPropagation() causes the first click after
        //map movement to be ignored by leaflet
        return buttonElement
    },
    _createButtonElement: function() {
        var element = $("<div class='leaflet-button' id='show-time-slider-button' title='Start Time Slider'><img src='/media/img/time-slider-button-disabled.png'></div>")[0]

        var button = this
        $(element).on("dblclick", function(e) {
            e.stopPropagation()
        })
        $(element).on("click", function(e) {
            e.stopPropagation() // see comment in onAdd
            if (!button.options.enabled) {
                button.options.enabled = true
                $(this).addClass("enabled")
                $(this).children("img").attr("src", "/media/img/time-slider-button-enabled.png")
                button.options.delegate.enableTimeSlider()
                button.showTooltip(this)
            }
            else {
                button.options.enabled = false
                $(this).removeClass("enabled")
                $(this).children("img").attr("src", "/media/img/time-slider-button-disabled.png")
                button.options.delegate.disableTimeSlider()
                button.hideTooltip(this)
            }
        })
        return element
    },
    hideTooltip: function(element) {
        $(this.options.tooltip.element).remove()
    },
    showTooltip: function(element) {
        $(element).append(this.options.tooltip.element)
    }
})

function TimeSliderBar(delegate, mapView) {
    this.delegate = delegate
    this.mapView = mapView
    this.barElement = $("<div id='time-slider-bar'></div>")[0]
    this.prevButton = $("<span class='time-slider-button' id='time-slider-button-prev'>Prev</span>")[0]
    this.textElement = $("<span id='time-slider-bar-text'></span>")[0]
    this.nextButton = $("<span class='time-slider-button' id='time-slider-button-next'>Next</span>")[0]
    this._leafletControl = null
    this.visible = null

    this.timelineElement = $("<div class='time-slider-timeline'></div>")[0]
    this.currentPosition = 0

    var bar = this
    $(this.prevButton).click(function() {
        if (bar.currentPosition > 0) {
            bar.currentPosition -= 1
        }
    })
    $(this.nextButton).click(function() {
        if (bar.currentPosition < (bar.delegate.numberOfTimeSliderItems() - 1)) {
            bar.currentPosition += 1
        }
    })

    $(this.barElement).append(this.timelineElement)
    $(this.barElement).append(this.prevButton)
    $(this.barElement).append(this.textElement)
    $(this.barElement).append(this.nextButton)
}

Object.defineProperty(TimeSliderBar.prototype, "timelineElement", {
    get: function() {
        return timelineElement
    },
    set: function(element) {
        var timelineChartElement = $("<span class='time-slider-timeline-chart'></span>")
        var timelineFirstYearElement = $("<span class='time-slider-timeline-first-year time-slider-button'>First</span>")
        var timelineLastYearElement = $("<span class='time-slider-timeline-last-year time-slider-button'>Last</span>")

        var years = this.delegate.yearsForTimeSlider()
        var firstYear = years[0]
        var lastYear = years[years.length-1]

        $(timelineFirstYearElement).text(firstYear)
        $(timelineLastYearElement).text(lastYear)

        var timelineChartWidth = 380
        var yearSpan = lastYear - firstYear
        var yearWidth = timelineChartWidth/(yearSpan+1)

        var lastYear = null
        for (var i = 0; i < years.length; ++i) {
            if (years[i] == lastYear) {
                continue
            }

            var yearDifference = years[i] - years[0]
            var leftDistance = yearDifference*yearWidth + 50

            var yearElement = $("<span></span>")
            yearElement.css({
                "display": "inline-block",
                "height": "20px",
                "width": (yearWidth - 1) + "px",
                "background-color": i == 0 ? "#253A71" : "#AAAAAA",
                "position": "absolute",
                "left": leftDistance+"px"
            })
            yearElement.attr("title", years[i])
            yearElement.attr("data-year", years[i])

            var bar = this
            yearElement.click(function() {
                var year = Number($(this).attr("data-year"))
                var position = years.indexOf(year)
                bar.currentPosition = position
            })

            $(timelineChartElement).append(yearElement)

            lastYear = years[i]
        }

        var bar = this
        $(timelineFirstYearElement).click(function() {
            bar.currentPosition = 0
        })
        $(timelineLastYearElement).click(function() {
            bar.currentPosition = bar.delegate.numberOfTimeSliderItems()-1
        })
    
        $(element).append(timelineFirstYearElement).append(timelineChartElement).append(timelineLastYearElement)

        timelineElement = element
    }
})

Object.defineProperty(TimeSliderBar.prototype, "currentPosition", {
    get: function() {
        return this._currentPosition
    },
    set: function(newValue) {
        if (this._currentPosition == newValue) {
            return
        }

        this._currentPosition = newValue
        currentPosition = newValue
        var numberOfItems = this.delegate.numberOfTimeSliderItems()
        
        //booleans
        var firstPosition = (newValue == 0)
        var lastPosition = ((numberOfItems - 1) == newValue)
        var noItems = (numberOfItems == 0)

        $(this.prevButton).removeClass("disabled")
        $(this.nextButton).removeClass("disabled")
        $(".time-slider-cell").removeClass("selected")
        $(sprintf(".time-slider-cell[data-position=%s]", currentPosition)).addClass("selected")
        $(sprintf(".time-slider-cell[data-position=%s] input[type=radio]", currentPosition)).prop("checked", true)

        if (firstPosition) {
            $(this.prevButton).addClass("disabled")
        }
        if (lastPosition || noItems) {
            $(this.nextButton).addClass("disabled")
        }

        $("#time-slider-bar span[data-year]").css("background-color", "#AAAAAA")
        $(sprintf("#time-slider-bar span[data-year=%s]", this.delegate.yearsForTimeSlider()[currentPosition])).each(function() {
            $(this).css("background-color", "#253A71")
        })

        var text = null

        if (numberOfItems > 0) {
            var item = this.delegate.itemForTimeSliderPosition(newValue)
            var layerDisplayName = item.LayerDisplayName
            var year = item.ContentDate.substring(0,4)
            text = sprintf("%s - \"%s\"", year, layerDisplayName)
            this.delegate.setTimeSliderPosition(newValue)
        }
        else {
            text = "No items at point"
        }
        
        numberOfItems > 0 ? this.delegate.itemForTimeSliderPosition(newValue).LayerDisplayName : "No items at selected point"
        $(this.textElement).text(text)
    }
})

Object.defineProperty(TimeSliderBar.prototype, "leafletControl", {
    get: function() {
        var barElement = this.barElement
        var bar = this
        var control = L.Control.extend({
            options: { position: "bottomleft" },
            onAdd: function(map) {
                L.DomEvent.disableClickPropagation(barElement)
                bar.visible = true
                return barElement
            },
            onRemove: function(map) {
                bar.visible = false
            }
        })
        if (!this._leafletControl) {
            this._leafletControl = new control()
        }
        return this._leafletControl
    }
})

function TableView(tableViewID, tableViewDelegate) {
    this.tableViewID = tableViewID
    this.delegate = tableViewDelegate
}

TableView.prototype.reloadData = function() {
    var elementID = sprintf("#%s", this.tableViewID)
    $(elementID).empty()
    var numSections = this.delegate.numberOfSections()

    for (var i = 0; i < numSections; i++) {
        var sectionID = sprintf("%s-section-%d", this.tableViewID, i)
        var sectionElement = sprintf("<div class='tableview-section' id='%s'></div>", sectionID)
        $(sprintf("#%s", this.tableViewID)).append(sectionElement)

        var delegate = this.delegate
        if (this.delegate.sectionSortable(i)) {
            var sortHandle = $(sprintf("#%s", sectionID)).sortable({
                axis: "y",
                handle: '.cell-sort-handle',
                items: 'div:not(.section-header, .section-footer)',
                start: function(e, ui) {
                    $(ui.item[0]).addClass("sorting")
                },
                stop: function(e, ui) {
                    var section = parseInt($(ui.item[0]).attr("data-section"))
                    delegate.orderChangedForSection(section)
                }
            })
        }
        this.reloadSection(i)
    }
}


TableView.prototype.reloadSection = function(section) {
    var delegate = this.delegate
    var sectionID = sprintf("#%s-section-%d", this.tableViewID, section)
    var numRows = delegate.numberOfRowsInSection(section)

    $(sectionID).empty()

    if (numRows > 0) {
        var header = delegate.headerForSection(section)
        if (header) { $(sectionID).append(header.element) }

        var range = Array.range(0, numRows)
        range = delegate.orderingForSection(section) == 1 ? range : range.reverse()

        $(range).each(function() {
            var row = this.valueOf()
    
            var cell = delegate.cellForRowInSection(row, section)
            var cellElement = cell.element
    
            $(sectionID).append(cellElement)

            if (cell.onAdd) {
                cell.onAdd()
            }
        })

        var footer = delegate.footerForSection(section)
        if (footer) { $(sectionID).append(footer.element) }
    }
}

TableView.prototype.removeRowInSection = function(row, section) {
    this.reloadSection(section)
}

function TableViewCollection(tableViews) {
    this.tableViews = tableViews
}

TableViewCollection.prototype.reloadData = function() {
    for (var i = 0; i < this.tableViews.length; ++i) {
        this.tableViews[i].reloadData()
    }
}

function SearchView(view_id, field_id_base, fields, delegate, submitButton, resetButton) {
    this.view_id = view_id
    this.element_id = sprintf("#%s",view_id)
    this.field_id_base = field_id_base
    this.delegate = delegate
    this.submitButton = submitButton || $("#search-button-submit")
    this.resetButton = resetButton || $("#search-button-reset")
    this.enabled = true
    
    for (var i = 0; i < fields.length; ++i) {
        this[sprintf("%s_field_id", fields[i])] = sprintf("#%s-%s", field_id_base, fields[i])
    }

    $(this.element_id).keypress(function(e) {
        if (e.which == ENTER_KEY_CODE) {
            delegate.searchRequested()
        }
    })

    $(this.location_field_id).bind("input", function() {
        delegate.searchOptions[SO_LOCATION_TEXT] = $(this).val().trim()
    })
    $(this.keyword_field_id).bind("input", function() {
        delegate.searchOptions[SO_KEYWORD_TEXT] = $(this).val().trim()
    })
    $(this.startyear_field_id).bind("input", function() {
        delegate.searchOptions[SO_START_YEAR] = $(this).val().trim()
    })
    $(this.endyear_field_id).bind("input", function() {
        delegate.searchOptions[SO_END_YEAR] = $(this).val().trim()
    })
    $(this.originator_field_id).bind("input", function() {
        delegate.searchOptions[SO_ORIGINATOR_TEXT] = $(this).val().trim()
    })
    $(this.datatype_field_id).bind("change", function() {
        delegate.searchOptions[SO_DATATYPE_TEXT] = $(this).val()
    })
    $(this.showpolygon_field_id).bind("click", function() {
        var checked = $(this).prop("checked")
        delegate.searchOptions[SO_SHOW_POLYGON] = checked
        delegate.searchOptions[SO_LIMIT_TO_LOCATION] = checked
        $("#gazetteer-showpolygon").prop("checked", checked)

        if (!checked) {
            delegate.gazetteerLayers.clearLayers()
            delegate.enteredLocationLayers.clearLayers()

            if (delegate.selectedGazetteerPolygon) {
                delegate.previousGazetteerPolygon = delegate.selectedGazetteerPolygon
                delegate.selectedGazetteerPolygon = null
                delegate.loadDataForMapBounds()
            }
            if (delegate.searchData[OSM_ID]) {
                delegate.searchData = {}
                delegate.loadDataForMapBounds()
            }
        }
        else if (checked && delegate.previousSearchOptions && delegate.previousSearchOptions[SO_LOCATION_TEXT]) {
            delegate.searchOptions[SO_LOCATION_TEXT] = delegate.previousSearchOptions[SO_LOCATION_TEXT]
            delegate.searchRequested()
        }
        else if (checked && delegate.previousGazetteerPolygon) {
            var p = delegate.previousGazetteerPolygon
            delegate.gazetteerPolygonSelected(p.id, p.type, p.name)
        }
    })

    $(this.submitButton).on("click", function(e) {
        delegate.searchRequested()
    })

    var searchView = this
    $(this.resetButton).on("click", function() {
        searchView.resetSearch()
    })
}

Object.defineProperty(SearchView.prototype, "placeholderLocation", {
    set: function(newValue) {
        $(this.location_field_id).attr("placeholder", sprintf("Enter a location (Currently: %s)", newValue))
    }
})

Object.defineProperty(SearchView.prototype, "placeholderText", {
    get: function() {
        return $(this.location_field_id).attr("placeholder")
    },
    set: function(newValue) {
        $(this.location_field_id).attr("placeholder", newValue)
    }
})

SearchView.prototype.resetSearch = function() {
    var delegate = this.delegate
    delegate.searchOptions = {}

    $(this.location_field_id).val("")
    $(this.keyword_field_id).val("")
    $(this.startyear_field_id).val("")
    $(this.endyear_field_id).val("")
    $(this.originator_field_id).val("")
    $(this.datatype_field_id).val("")
    $(this.showpolygon_field_id).prop("checked", false)

    delegate.gazetteerLayers.clearLayers()
    delegate.enteredLocationLayers.clearLayers()

    if (delegate.selectedGazetteerPolygon) {
        delegate.previousGazetteerPolygon = null
        delegate.selectedGazetteerPolygon = null
    }
    if (delegate.searchData[OSM_ID]) {
        delegate.searchData = {}
    }
    delegate.loadDataForMapBounds()
}

SearchView.prototype.disableSearch = function() {
    $(this.submitButton).addClass("disabled")
    $(this.submitButton).text("Searching")
    $(this.submitButton).off("click")
    this.enabled = false
}

SearchView.prototype.enableSearch = function() {
    var delegate = this.delegate
    $(this.submitButton).removeClass("disabled")
    $(this.submitButton).text("Search")
    if (!this.enabled) {
        $(this.submitButton).on("click", function() {
            delegate.searchRequested()
        })
    }
    this.enabled = true
}

function BoundedItem(dictionary, collection) {
    if (dictionary.Location && dictionary.Location.indexOf("{") != 0) {
        dictionary.Location = sprintf("{%s}", dictionary.Location)
    }
    if (dictionary.Location) {
        dictionary.Location = JSON.parse(dictionary.Location); 
    }
    else {
        dictionary.Location = { "wms": ["/geoserver/wms"] }
    }

    for (var k in dictionary) {
        this[k] = dictionary[k]
    }
    this.collection = collection
    this.bounds = L.latLngBounds([this.MinY, this.MinX], [this.MaxY, this.MaxX])
    this.previewOutline = L.rectangle(this.bounds)
    this.selected = false
    this._highResLayer = false

    var item = this
    if (this.isVectorType) {
        this.mapLayer = new DeferredGeoJSON(this.wfsURL)
        this.mapLayer.options = new LeafletOptions(this.mapLayer.options)
    }
    else if (this.DataType == "Book") {
        var circleText = sprintf("%s\n%s", this.ContentDate.split("-")[0], this.LayerDisplayName.split(" - ")[1].replace("Section", "§"))
        var fontSize = 12
        var marker = new L.Marker.SVGMarker.BookMarker(this.bounds.getCenter(), {"iconOptions": { "circleText": circleText, "fontSize": fontSize }})
        marker.bindPopup(sprintf("<div>%s</div><a href='/media/pdf/%s.pdf' target='_blank'>View PDF</a>", this.LayerDisplayName, this.Name))

        var group = new L.LayerGroup()
        group.options = new LeafletOptions(group.options)
        group.addLayer(marker)
        group.addLayer(new L.Rectangle(this.bounds))
        group.options.opacity = 1

        this.mapLayer = group
    }
    else {
        this.mapLayer = L.tileLayer.wms(this.wmsURL, {
            layers: this.Name,
            format: "image/png",
            transparent: true
        })
    }
}

Object.defineProperty(BoundedItem.prototype, "highResLayer", {
    get: function() {
        return this._highResLayer
    },
    set: function(highRes) {
        this._highResLayer = highRes

        if (highRes) {
            this.mapLayer.options.tileSize = 128
            this.mapLayer._map.setMaxZoom(17)
            this.mapLayer.options.maxZoom = 17
            this.mapLayer.options.zoomOffset = 1
        }
        else {
            this.mapLayer.options.tileSize = 256
            this.mapLayer._map.setMaxZoom(18)
            this.mapLayer.options.maxZoom = 18
            this.mapLayer.options.zoomOffset = 0
        }

        this.mapLayer._update()
    }
})

Object.defineProperty(BoundedItem.prototype, "isVectorType", {
    get: function() {
        return ["Point", "Polygon", "Line"].includes(this.DataType)
    }
})

Object.defineProperty(BoundedItem.prototype, "wfsURL", {
    get: function() {
        if (this.Location && this.Location["wfs"] && this.WorkspaceName && this.Name) {
            var url = this.Location["wfs"].replace("http://","")
            return sprintf("/external_wfs/%s?request=GetFeature&typeName=%s:%s&outputFormat=application/json&srsName=EPSG:4326", url, this.WorkspaceName, this.Name) 
        }
        else {
            return null
        }
    }
})

Object.defineProperty(BoundedItem.prototype, "wmsURL", {
    get: function() {
        var url = this.Location && (typeof this.Location.wms) == "object"  ? this.Location.wms[0] : null
        return url
    }
})

Object.defineProperty(BoundedItem.prototype, "secureWMS", {
    get: function() {
        return this.wmsURL.startsWith("https://")
    }
})

Object.defineProperty(BoundedItem.prototype, "willDisableGeolocation", {
    get: function() {
        return L.Browser.safari && !this.isVectorType && !this.secureWMS
    }
})

Object.defineProperty(BoundedItem.prototype, "thumbnailURL", {
    get: function() {
        var url = this.Location && (typeof this.Location.wms) == "object"  ? this.Location.wms[0] : null

        if (!url.startsWith("https://")) {
            url = sprintf("/external_reflect/%s", url.replace(/^http:\/\//, ""))
        }

        return url
    }
})

Object.defineProperty(BoundedItem.prototype, "contentYear", {
    get: function() { return this.ContentDate.substring(0,4) }
})

function BoundedItemCell(item, row, section, delegate, infoButtonDelegate, allowSelection, mapView) {
    this.item = item
    this.selected = item.selected
    this.row = row
    this.section = section
    this.delegate = delegate
    this.infoButtonDelegate = infoButtonDelegate
    this.allowSelection = allowSelection
    this.mapView = mapView
    this.opacityValue = 100
}

BoundedItemCell.prototype.enableHiResLayer = function() {
    var item = this.item

    item.mapLayer.remove()

    var options = {
        layers: item.Name,
        format: "image/png",
        transparent: true,
        detectRetina: true
    }
    item.mapLayer = L.tileLayer.wms(item.wmsURL, options)
    item.mapLayer.options.originalTileSize = item.mapLayer.options.tileSize

    this.mapView.visibleLayers.addLayer(item.mapLayer)
}

Object.defineProperty(BoundedItemCell.prototype, "element", {
    get: function() {
        var item = this.item
        var collectionName = item.collection
        var map = this.mapView.map
        var selectedClass = this.selected ? " selected" : ""
        var cell = $(sprintf("<div class='bounded-item-cell tableview-row%s' data-row='%d' data-section='%d' data-layer-id='%s'></div>", selectedClass, this.row, this.section, item.LayerId))

        if (item.DataType == "Book" || item.isVectorType) {
            $(cell).addClass("unsortable")
        }

        if (this.section > 1) {
            $(cell).attr("data-collection", collectionName)
        }

        var selectedField = $("<input type='checkbox' class='cell-field selected-field'>")
        selectedField.attr("checked", this.selected)

        var delegate = this.delegate
        var infoButtonDelegate = this.infoButtonDelegate
        var row = this.row
        var section = this.section

        if (this.allowSelection) {
            $(selectedField).click(function(e) {
                e.preventDefault()
                delegate.selectedCellForRowInSection(row, section)
            })
        }
        else {
            $(selectedField).attr("disabled", "disabled")

            if (!this.selected) {
                $(selectedField).css("visibility", "hidden")
            }
        }
        
        var layerDisplayName = this.item.LayerDisplayName
        layerDisplayName = sprintf("%s (%s)", layerDisplayName, this.item.contentYear)
        var institution = this.item.Institution
        var layerDisplayNameField = $(sprintf("<span class='layerdisplayname-field'>%s</span>", layerDisplayName))
        var institutionField = $(sprintf("<img class='institution-field' src='/media/img/logo_%s.png' title='%s' alt='%s Logo'>", institution.toLowerCase(), institution, institution))
        var infoButton = new InfoButton(item, delegate.proxyURL, delegate.mapView)

        cell.append(selectedField)
        cell.append(layerDisplayNameField)
        cell.append(institutionField)
        cell.append(infoButton.element)

        if (L.Browser.safari && !item.isVectorType && !item.secureWMS) {
            var insecureItemField = $("<img class='insecure-item-field' src='/media/img/insecure-item.png' title='Selecting this item will disable geolocation' alt='Insecure Item'>")
            cell.append(insecureItemField)
        }

        if (this.selected) {
            var boundedItemCell = this
            var sortHandle = $("<span class='image-control cell-sort-handle' title='Click and drag to order layer'></span>")
            var opacityField = $("<span class='opacity-field'><span class='opacity-text'>Opacity: </span></span>")

            if (item.isVectorType || item.DataType == "Book") {
                $(sortHandle).attr("title", "Books and vector layers will not change their map layering.")
            }
            
            var opacityControl = new OpacityControl(this.item, this)
            opacityField.append(opacityControl.element)


            var centerButton = new CenterButton(item, this.mapView.map)

            if (delegate.sectionSortable(section)) {
                cell.append(sortHandle)
            }
            cell.append(opacityField)

            if (!item.isVectorType && item.DataType != "Book") {
                var switchResButton = new SwitchResButton(this.item, this.mapView)
                cell.append(switchResButton.element)
            }

            cell.append(centerButton.element)

            if (item.isVectorType) {
                var statusField = $("<span class='status-field'></span>")
                if (item._bytesLoaded) {
                    var bytes = item._bytesLoaded
                    var sizeText = bytes > 1000000 ? sprintf("%.1fMB", bytes / 1000000) : sprintf("%dKB", bytes / 1000)
                    $(statusField).text(sizeText)
                }
                cell.append(statusField)
            }

            if (item.isVectorType || item.DataType == "Book") {

                var colorField = $("<span class='color-field'>Color: </span>")
                var colorControlContainer = $("<span class='color-control-container'></span>")
                var colorControl = $("<span class='color-control'></span>")
                colorControlContainer.append(colorControl)
                colorField.append(colorControlContainer)
                cell.append(colorField)

                if (item.color) {
                    var color = item.color

                    var transparentColor = sprintf("rgba(%s,%s,%s,0.4)",color[0],color[1],color[2])
                    var solidColor = sprintf("rgb(%s,%s,%s)",color[0],color[1],color[2])

                    colorControl.css("background-color", transparentColor)
                    colorControl.css("border", sprintf("1px solid %s", solidColor))
                }

                colorControl.click(function() {
                    var colorPicker = new ColorPicker({
                        "selectedColor": function(color) {
                            var transparentColor = sprintf("rgba(%s,%s,%s,0.4)",color[0],color[1],color[2])
                            var solidColor = sprintf("rgb(%s,%s,%s)",color[0],color[1],color[2])

                            item.color = color

                            var colorControls = $(sprintf(".bounded-item-cell[data-layer-id=\"%s\"] .color-control", item.LayerId))
                            colorControls.css("background-color", transparentColor)
                            colorControls.css("border", sprintf("1px solid %s", solidColor))
                            item.mapLayer.setStyle({
                                "color": solidColor
                            }, item.LayerDisplayName)
                        }
                    }, item.LayerDisplayName)
                    colorPicker.open()
                })
            }
        }

        $(cell).hover(
            function() {
                delegate.hoverStartedForRowInSection(row, section)
            }, function() {
                delegate.hoverEndedForRowInSection(row, section)
            }
        )

        return cell
    }
})

function ElementCell(element, cellClass) {
    this.element = $(element)
    this.cellClass = cellClass
}

function TextCell(textElement, cellClass) {
    this.text = textElement
    this.cellClass = cellClass 
}

Object.defineProperty(TextCell.prototype, "element", {
    get: function() {
        var cellClass = this.cellClass || "tableview-row"
        var cell = $(sprintf("<div class='%s no-highlight text-cell'></div>", cellClass))
        cell.append(this.text)

        return cell
    }
})

function NoResultsCell() {
    this.text = "No items were found within the map's bounds using the entered search parameters."
}
NoResultsCell.prototype = TextCell.prototype

function EmptyCollectionCell() {
    this.text = "This collection does not have any unselected item within the map's bounds."
}
EmptyCollectionCell.prototype = TextCell.prototype

function NoSelectedItemsCell() {
    this.text = "No items selected."
}
NoSelectedItemsCell.prototype = TextCell.prototype

function LoadingCell() {
    this.loadingIndicatorElement = $("<div></div>")
}

Object.defineProperty(LoadingCell.prototype, "element", {
    get: function() {
        var cell = $("<div class='tableview-row no-highlight loading-cell'></div>")
        cell.append(this.loadingIndicatorElement)

        return cell
    }
})

Object.defineProperty(LoadingCell.prototype, "onAdd", {
    get: function() {
        this.loadingIndicatorElement.spin()
    }
})

function PaginatingCell(page, total, section, delegate) {
    this.page = page
    this.total = total
    this.section = section
    this.delegate = delegate
}

Object.defineProperty(PaginatingCell.prototype, "element", {
    get: function() {
        var cellElement = $("<div class='tableview-row text-cell paginating-cell no-highlight'></div>")
        var prevButton = $("<a class='text-control prev-button'>Prev</a>")
        var nextButton = $("<a class='text-control next-button'>Next</a>")
        var cellText = $(sprintf("<span>Page %d of %d</span>", this.page, this.total))

        var cell = this
        $(prevButton).click(function() { cell.delegate.paginatingCellSetPageForSection(cell.page - 1, cell.section) })
        $(nextButton).click(function() { cell.delegate.paginatingCellSetPageForSection(cell.page + 1, cell.section) })
        $(prevButton).css("visibility", this.page == 1 ? "hidden" : "visible")
        $(nextButton).css("visibility", this.page == this.total ? "hidden" : "visible")

        $(cellElement).append(prevButton, cellText, nextButton)

        return cellElement
    }
})

function TimeSliderTableViewCell(row, section, item, tableViewDelegate, timeSliderBar, selected) {
    this.item = item
    this.position = row
    this.section = section
    this.tableViewDelegate = tableViewDelegate
    this.timeSliderBar = timeSliderBar
    this.selected = selected
}

Object.defineProperty(TimeSliderTableViewCell.prototype, "element", {
    get: function() {
        var cell = this

        var element = $(sprintf("<div class='time-slider-cell tableview-row%s' data-position='%s' data-layer-id='%s'></div>", this.selected ? " selected" : "", this.position, this.item.LayerId))

        var checkbox = $(sprintf("<input type='checkbox' %s>", this.item.selected ? "checked" : ""))
        $(checkbox).click(function(e) {
            e.stopPropagation()
            cell.item.reloadSection = true
            cell.item.selected = $(this).prop("checked")
            cell.tableViewDelegate.selectedCellForRowInSection(cell.position, cell.section)
        })
        element.append(checkbox)
    
        element.append($(sprintf("<span class='year-field'>%s</span>", this.item.contentYear)))
        element.append($(sprintf("<span class='title-field'>%s</span>", this.item.LayerDisplayName)))

        var centerButton = new CenterButton(this.item, this.timeSliderBar.mapView.map)
        element.append(centerButton.element)

        var switchResButton = new SwitchResButton(this.item, this.timeSliderBar.mapView)
        element.append(switchResButton.element)

        var proxyURL = this.timeSliderBar.delegate.proxyURL
        var infoButton = new InfoButton(this.item, proxyURL, this.timeSliderBar.mapView)
        element.append(infoButton.element)


        //conver to object
        var opacityField = $("<span class='opacity-field'><span class='opacity-text'>Opacity: </span></span>")
        
        var opacityControl = new OpacityControl(this.item, this)
        opacityField.append(opacityControl.element)
        element.append(opacityField)

        var cell = this
        element.click(function() {
            cell.tableViewDelegate.selectedCellForRowInSection(cell.position, cell.section)
        })

        var delegate = this.tableViewDelegate
        $(element).hover(
            function() {
                delegate.hoverStartedForRowInSection(cell.position, cell.section)
            }, function() {
                delegate.hoverEndedForRowInSection(cell.position, cell.section)
            }
        )

        return element
    }
})

function SectionHeader(mainText, subText, section, extraClasses) {
    this.mainTextElement = $("<span class='section-header-main-text'></span>").append(mainText)
    this.subTextElement = $(sprintf("<span class='section-header-sub-text'>%s</span>", subText || ""))
    this.section = section
    this.extraClasses = extraClasses || ""
}

Object.defineProperty(SectionHeader.prototype, "html", {
    get: function() {
        return sprintf("<div class='section-header %s'><span class='section-header-main-text'>%s</span><span class='section-header-sub-text'>%s</span></div>", 
            this.extraClasses, this.mainText, this.subText)
    }
})

Object.defineProperty(SectionHeader.prototype, "element", {
    get: function() {
        var headerElement = $(sprintf("<div class='section-header %s' data-section='%d'></div>", this.extraClasses, this.section))
        headerElement.append(this.mainTextElement)
        headerElement.append(this.subTextElement)
        return headerElement
    }
})

function CollapsingSectionHeader(mainText, section, delegate, tableViewID) {
    SectionHeader.call(this, mainText, null, section, "rounded-for-show-button")

    var collapsed = delegate.collapseStateForSection(section)

    var buttonText = null
    if (collapsed) {
        var sectionID = sprintf("#%s-section-%d", tableViewID, section)
        $(sprintf("#%s-section-%d", tableViewID, section)).addClass("hidden")
        buttonText = "Show"
    }
    else {
        buttonText = "Hide"
    }

    this.subTextElement = $(sprintf("<span class='section-header-sub-text'><span class='text-control show-button'>%s</span></span>", buttonText))
    this.delegate = delegate

    $(this.subTextElement).click(function() {
        var tableViewSection = $(sprintf("#%s-section-%d", tableViewID, section))

        if (tableViewSection.hasClass("hidden")) {
            tableViewSection.removeClass("hidden")
            $(this).children(".show-button").text("Hide")
            delegate.collapseStateChangedForSection(section, false)
        }
        else {
            tableViewSection.addClass("hidden")
            $(this).children(".show-button").text("Show")
            delegate.collapseStateChangedForSection(section, true)
        }
    })
}
CollapsingSectionHeader.prototype = SectionHeader.prototype

function SectionFooter(mainText) {
    this.mainText = mainText || ""
}

Object.defineProperty(SectionFooter.prototype, "html", {
    get: function() {
        return sprintf("<div class='section-footer'><span class='section-footer-main-text'>%s</span></div>", this.mainText)
    }
})

Object.defineProperty(SectionFooter.prototype, "element", {
    get: function() {
        return $(this.html)[0]
    }
})

function DownloadFooter(delegate, urlDelegate) {
    this.delegate = delegate
    this.urlDelegate = urlDelegate || delegate
}

Object.defineProperty(DownloadFooter.prototype, "element", {
    get: function() {
        var element = $(new SectionFooter().html)
        var downloadButtonElement = $("<a class='download-button text-control'>Download</a>")  
        var delegate = this.delegate
        var urlDelegate = this.urlDelegate

        
        var emailInputElement = $("<input type='text' placeholder='Enter your email address' style='width: 380px'>")
        var dialogIntro = $("<p>All downloaded files include metadata files in FGDC format.</p>")

        var formats = {
            "json": "GeoJSON",
            "gml": "GML",
            "kml": "KML",
            "shapefile": "Shape file"
        }

        var formatInputElement = $("<select></select>")
        for (var value in formats) {
            formatInputElement.append(sprintf("<option value='%s'>%s</option", value, formats[value]))
        }
        var downloadDialogElement = $("<div>A link to a zip file containing your selected items will be sent to the following address:<div>")
            
        var hasExternalItems = false
        for (var i = 0; i < delegate.selectedItems.length; ++i) {
            var item = delegate.selectedItems[i]

            if (!item.LayerId.startsWith("UNH")) {
                hasExternalItems = true
                break
            }
        }

        if (hasExternalItems) {
            var formatElement = $("<div style='margin-bottom: 1em'>Select a format for vector data: </div>").append(formatInputElement)
            downloadDialogElement.prepend(formatElement).prepend(dialogIntro)
        }
        else {
            downloadDialogElement.prepend(dialogIntro)
        }
        downloadDialogElement.append(emailInputElement)
        
        var downloadDialog = $(downloadDialogElement).dialog({
            autoOpen: false,
            title: "Enter email address",
            buttons: [{
                text: "Request Download",
                click: function() {
                    var emailAddress = $(emailInputElement).val()
                    var wfsFormat = $(formatInputElement).val()
                    delegate.downloadRequested(emailAddress, wfsFormat)
                    $(this).dialog("close")
                }
            }, {
                text: "Close",
                click: function() { $(this).dialog("close") }
            }]
        })

        $(downloadButtonElement).click(function() {
            $(downloadDialog).dialog("open")
        })
        $(element).append(downloadButtonElement)

        var linkButtonElement = $("<a class='link-button text-control'>Share</a>")

        $(linkButtonElement).click(function() {
            var linkDialogElement = $(sprintf("<div><div><b>Link for selected layers</b></div><textarea readonly>%s</textarea></div>", urlDelegate.urlWithLayers))

            $(linkDialogElement).dialog({
                dialogClass: "link-dialog",
                title: "Share Selected Items",
                buttons: [{
                    text: "Close",
                    click: function() { $(this).dialog("close") }
                }],
                open: function() {
                    $(this).children("textarea").select()
                }
            })
        })

        $(element).append(linkButtonElement)

        var exportButtonElement = $("<a class='export-button text-control'>WFS Export</a>")

        var hasVectorLayers = false
        for (var i = 0; i < delegate.selectedItems.length; ++i) {
            var item = delegate.selectedItems[i]
            if (item.isVectorType) { 
                hasVectorLayers = true
                break
            }
        }

        if (hasVectorLayers) {
            $(exportButtonElement).click(function() {
                var exportDialogElement = $("<div></div>")
                for (var i = 0; i < delegate.selectedItems.length; ++i) {
                    var item = delegate.selectedItems[i]
                    if (item.isVectorType) {
                        exportDialogElement.append(sprintf("<div><b>WFS Link for <i>%s</i></b><textarea>%s</textarea></div>", item.LayerDisplayName, item.wfsURL.replace("/external_wfs/", "http://")))
                    }
                }

                $(exportDialogElement).dialog({
                    dialogClass: "link-dialog",
                    title: "WFS Export",
                    buttons: [{
                        "text": "Close",
                        "click": function() { $(this).dialog("close") }
                    }]
                })
            })
        }
        else {
            $(exportButtonElement).addClass("disabled")
        }

        $(element).append(exportButtonElement)

        var clearButtonElement = $("<a class='clear-button text-control'>Clear</a>")
        $(clearButtonElement).click(function() {
            delegate.clearLayers()
        })

        $(element).append(clearButtonElement)

        return element
    }
})

function SwitchResButton(item, mapView) {
    this.item = item
    this.mapView = mapView
}

Object.defineProperty(SwitchResButton.prototype, "element", {
    get: function() {
        var item = this.item
        var mapView = this.mapView
    
        var switchResButton = $(sprintf("<span data-layer='%s' class='switch-res-button' title='Switch Image Resolution'></span>", item.Name))
    
        var text = null
        if (item.highResLayer) {
            $(switchResButton).addClass("high")
        }
        else {
            $(switchResButton).addClass("low")
        }

        $(switchResButton).click(function(e) {
            if (!item.mapLayer._map) { 
                return
            }

            item.highResLayer = !item.highResLayer //property that handles actual switching

            if (item.highResLayer) {
                $(sprintf(".switch-res-button[data-layer='%s']", item.Name)).removeClass("low").addClass("high")
            }
            else {
                $(sprintf(".switch-res-button[data-layer='%s']", item.Name)).removeClass("high").addClass("low")
            }
        })
    
        return switchResButton
    }
})

function CenterButton(item, map) {
    this.item = item
    this.map = map
}

Object.defineProperty(CenterButton.prototype, "element", {
    get: function() {
        var centerButton = $("<span title='Center map on item' class='center-button text-control'>Center</span>")

        var map = this.map
        var item = this.item
        $(centerButton).click(function(e) {
            e.stopPropagation()
            map.fitBounds([[item.MinY, item.MinX], [item.MaxY, item.MaxX]])
        })
        return centerButton
    }
})

function InfoButton(item, proxyURL, mapView) {
    this.item = item
    this.proxyURL = proxyURL
    this.mapView = mapView
}

Object.defineProperty(InfoButton.prototype, "element", {
    get: function() {
        var delegate = this.delegate
        var item = this.item
        var itemURL = sprintf("%s/layer?id=%s", this.proxyURL, item.LayerId)
        var abstractURL = sprintf("%s/abstract?id=%s", this.proxyURL, item.LayerId)
        var metadataURL = sprintf("%s/metadata?id=%s", this.proxyURL, item.LayerId)
        var element = $(sprintf("<a class='text-control info-button dialog-button' title='Click for more info'>i</a>", itemURL))

        var dialogSetup = function(element, title) {
            var settings = { 
                title: title,
                buttons: [{
                    text: "Close",
                    click: function() { 
                        $(this).dialog("close") 
                    }
                }],
                dialogClass: "info-dialog",
                open: function() {
                    $(this).children(".preview-image-container").spin().addClass("loading")
                }
            }
            var dialog = $(element).dialog(settings)
        }

        var infoButton = this
        $(element).click(function(e) {
            e.stopPropagation()
            var dialogText = $("<div class='dialog-text'></div>")
                .append(sprintf("<div><b>Content Year</b> %s</div>", item.contentYear))
                .append(sprintf("<div><b>Data Type</b> %s</div>", item.DataType))
                .append(sprintf("<div style='width: 190px'><b>Originator</b> %s</div>", item.Originator))
                .append("<br/>")
                .append(sprintf("<div><a href='%s' target='_blank'>View Main Record</a></div>", itemURL))
                .append(sprintf("<div><a href='%s' target='_blank'>Download Abstract</a></div>", abstractURL))
                .append(sprintf("<div><a href='%s' target='_blank'>Download Metadata</a></div>", metadataURL))

            var dialogElement = $("<div></div>").append(dialogText)


            if (item.selected && ["Point", "Line", "Polygon"].indexOf(item.DataType) != -1) {
                var viewJSONLink = $(sprintf("<div><a href='%s' target='_blank'>View Source Data</a></div>", item.wfsURL))
                dialogElement.append(viewJSONLink)
            }

            var imageElement = $(sprintf("<img class='preview-image' src='%s/reflect?layers=%s'>", item.thumbnailURL, item.Name))

            var nw = L.latLng(item.MaxY, item.MinX)
            var ne = L.latLng(item.MaxY, item.MaxX)
            var se = L.latLng(item.MinY, item.MaxX)

            nw = infoButton.mapView.map.project(nw)
            ne = infoButton.mapView.map.project(ne)
            se = infoButton.mapView.map.project(se)

            if (nw.distanceTo(ne) > ne.distanceTo(se)) {
                $(imageElement).addClass("wide")
            }
            else {
                $(imageElement).addClass("tall")
            }

            var imageElementContainer = $("<div class='preview-image-container'></div>")
            imageElementContainer.append(imageElement)
            dialogElement.prepend(imageElementContainer)

            $(imageElement).on("load", function() {
                $(this).parent().spin(false).removeClass("loading")
            })

            dialogSetup(dialogElement, item.LayerDisplayName)
        })

        return element
    }
})

function OpacityControl(item, cell) {
    this.item = item
    this.cell = cell
}

Object.defineProperty(OpacityControl.prototype, "element", {
    get: function() {
        var item = this.item
        var cell = this.cell

        var opacityControl = null

        if (/(Trident)|(MSIE)/.test(navigator.userAgent)) {
            opacityControl = $("<input type='text' style='width: 2em'>")
        }
        else {
            opacityControl = $("<input type='range' class='opacity-control'>")
        }

        opacityControl.val(item.mapLayer.options.opacity*100)

        opacityControl.bind("input", function() {
            var opacity = parseInt($(this).val())
            var opacityControlSelector = sprintf(".tableview-row[data-layer-id='%s'] .opacity-control", item.LayerId)
            $(opacityControlSelector).val(opacity)

            if (opacity > -1) {
                opacity = opacity > 100 ? 100 : opacity < 0 ? 0 : opacity
                $(this).val(opacity)
                cell.opacityValue = opacity
                opacity /= 100
                item.mapLayer.setOpacity(opacity)
            }
            else {
                $(this).val("")
            }
        })

        return opacityControl
    }
})

function GazetteerMenu(gazetteerButtonID, gazetteerBaseURL, gazetteerDelegate, searchViewDelegate) {
    this.buttonID = gazetteerButtonID
    this.url = gazetteerBaseURL
    this.delegate = gazetteerDelegate
    this.searchViewDelegate = searchViewDelegate || this.delegate
    this.tableView = new TableView("gazetteer-tableview", this)
    this.menu = $("<div id='gazetteer-tableview' style='overflow: scroll'></div>")
    this.currentEntries = null
    this.currentSelection = null
    this.previousSelections = []
    this.entries = {
        "states": {},
        "counties": {},
        "municipalities": {}
    }
    this.areaTypeForEntryType = {
        "states": "state",
        "counties": "county",
        "municipalities": "municipality"
    }
    this.nextTypeForEntryType = {
        "states": "counties",
        "counties": "municipalities",
        "municipalities": null
    }
    this.previousTypeForEntryType = {
        "states": null,
        "counties": "states",
        "municipalities": "counties"
    }

    //create dialog
    var tableView = this.tableView
    $(this.menu).dialog({
        autoOpen: false,
        buttons: [{
            text: "Close",
            click: function() { $(this).dialog("close") }
        }],
        maxHeight: 600,
        open: function() {
            $(this).css("overflow-x", "hidden")
            $(this).css("overflow-y", "scroll")
            tableView.reloadSection(0)
        },
        resizeable: false,
        title: "Gazetteer"
    })

    //load initial data
    this.currentSelection = {"name": "US", "id": "us", "type": "states"}

    this.loadEntriesForTypeAndID("states", "us")

    //show menu on click
    var gazetteer = this
    $(this.jqueryID).click(function() {
        $(gazetteer.menu).dialog("open")
    })
}

Object.defineProperty(GazetteerMenu.prototype, "jqueryID", {
    get: function() { return "#" + this.buttonID }
})

var gmp = GazetteerMenu.prototype

gmp.loadEntriesForTypeAndID = function(type, id) {
    if (this.entries[type][id]) {
        this.currentEntries = this.entries[type][id]
        this.tableView.reloadData()
    }
    else {
        var url = sprintf("%s/%s?id=%s", this.url, type, id)
        var gazetteer = this

        $.ajax(url, {
            success: function(data) {
                gazetteer.entries[type][id] = data.response
                gazetteer.currentEntries = gazetteer.entries[type][id]
                gazetteer.tableView.reloadData()
            }
        })
    }
}

gmp.nextEntryTypeSelectedForRowInSection = function(row, section) {
    var entry = this.currentEntries[row]
    
    this.previousSelections.push(this.currentSelection)
    this.currentSelection = {"name": entry.name, "id": entry.id, "type": this.nextTypeForEntryType[this.currentSelection.type]}

    this.loadEntriesForTypeAndID(this.currentSelection.type, this.currentSelection.id)
}

gmp.previousEntryTypeSelected = function() {
    this.currentSelection = this.previousSelections.pop()

    this.loadEntriesForTypeAndID(this.currentSelection.type, this.currentSelection.id)
}

//TableView delegate methods for gazetteer
gmp.numberOfSections = function() {
    return 2
}

gmp.numberOfRowsInSection = function(section) {
    if (section == 0) {
        return 1
    }
    return this.currentEntries.length || 1
}

gmp.cellForRowInSection = function(row, section) {
    if (section == 0) {
        var gazetteer = this

        var element = $("<span style='display: inline-block; text-align: center; width: 100%'></span>")
        var label = $("<label>Show and limit to location outline</label>")
        var checkbox = $("<input id='gazetteer-showpolygon' type='checkbox'>")
        var checked = this.searchViewDelegate.searchOptions[SO_SHOW_POLYGON]
        checkbox.prop("checked", checked)
        $(checkbox).click(function() {
            var state = gazetteer.searchViewDelegate.searchOptions[SO_SHOW_POLYGON]
            gazetteer.searchViewDelegate.searchOptions[SO_SHOW_POLYGON] = !state
            gazetteer.searchViewDelegate.searchOptions[SO_LIMIT_TO_LOCATION] = !state
            //TODO
            //remove explicit search field id
            $("#search-field-showpolygon").prop("checked", !state)
            if (state) {
                gazetteer.delegate.gazetteerPolygonUnselected()
            }
            else if (!state && gazetteer.delegate.previousGazetteerPolygon){
                var p = gazetteer.delegate.previousGazetteerPolygon
                gazetteer.delegate.gazetteerPolygonSelected(p.id, p.type, p.name)
            }
        })
        element.append(label.prepend(checkbox))
        return new ElementCell(element)
    }

    if (this.currentEntries == 0 && row == 0) {
        return new TextCell(sprintf("No %s available.", this.currentSelection.type), "gazetteer-row")
    }

    var entry = this.currentEntries[row]
    
    return new GazetteerEntryCell(entry, row, section, this)
}

gmp.hoverStartedForRowInSection = function(row, section) {
}

gmp.hoverEndedForRowInSection = function(row, section) {
}

gmp.selectedCellForRowInSection = function(row, section) {
    if (section == 0) {
        var checked = this.searchDelegate
    }

    var entry = this.currentEntries[row]
    var areaType = this.areaTypeForEntryType[this.currentSelection.type]
    this.delegate.gazetteerPolygonSelected(entry.id, areaType, sprintf("%s, %s", entry.name, this.currentSelection.name))
}

gmp.headerForSection = function(section) {
    if (section == 1) {
        return null
    }

    var previousSelection = this.previousSelections.length ? this.previousSelections[this.previousSelections.length-1] : null

    var mainText = sprintf("%s", this.currentSelection.name)
    var subText = previousSelection ? sprintf("< %s", previousSelection.name) : null
    var header = new SectionHeader(mainText, subText, section)

    if (previousSelection) {
        var gazetteer = this
        header.subTextElement.click(function() {
            gazetteer.previousEntryTypeSelected()
        })
    }

    return header
}

gmp.footerForSection = function(section) {
    return null
}

gmp.sectionSortable = function(section) {
    return false
}

gmp.orderingForSection = function(section) {
    return 1
}

gmp.orderChangedForSection = function(section) {
}

//end of gazetteer TableView delegate methods

function GazetteerEntryCell(entry, row, section, delegate) {
    this.entry = entry
    this.delegate = delegate
    this.row = row
    this.section = section
}

Object.defineProperty(GazetteerEntryCell.prototype, "element", {
    get: function() {
        var entryCell = this
        var cell = $(sprintf("<label class='gazetteer-row' data-row='%d' data-section='%d' data-id='%s'></label>", this.row, this.section, this.entry.id))
        var entryLabel = $(sprintf("<span class='entry-name'>%s</span>", this.entry.name))
        var entryLabelSelect = $("<span class='entry-select'>Select </span>")
        entryLabel.prepend(entryLabelSelect)
        cell.append(entryLabel)

        entryLabel.click(function(e) {
            entryCell.delegate.selectedCellForRowInSection(entryCell.row, entryCell.section)
        })

        var nextEntryType = this.delegate.nextTypeForEntryType[this.delegate.currentSelection.type]
        if (nextEntryType) {
            var nextButton = $("<span class='text-control borderless next-type-button'></span>")

            if (this.entry.next_entries) {
                var typeText = null
                
                if (this.entry.name == "Louisiana" && this.entry.id == "22") {
                    typeText = "Parishes"
                }
                else if (this.entry.name == "Alaska" && this.entry.id == "02") {
                    typeText = "Burroughs and CAs"
                }
                else if (nextEntryType == "municipalities") {
                    typeText = this.entry.next_entries == 1 ? "Subdivision" : "Subdivisions"
                }
                else {
                    typeText = this.entry.next_entries == 1 ? this.delegate.areaTypeForEntryType[nextEntryType].capitalize() : nextEntryType.capitalize()
                }
                var buttonText = sprintf("%s %s >", this.entry.next_entries, typeText)
                nextButton.text(buttonText)

                var viewText = $("<span class='entry-view'>View </span>")
                nextButton.prepend(viewText)

                nextButton.click(function(e) {
                    e.preventDefault()
                    entryCell.delegate.nextEntryTypeSelectedForRowInSection(entryCell.row, entryCell.section)
                })

                var orText = "<span class='or-text'>or</span>"
                cell.append(orText)
            }
            else {
                var buttonText = sprintf("No %s available.", nextEntryType)
                nextButton.text(buttonText)
                nextButton.addClass("disabled")
                cell.addClass("no-next-type")
            }

            cell.append(nextButton)
        }
        else {
            cell.addClass("no-next-type")
        }

        return cell
    }
})

function ColorPicker(delegate, itemName) {
    this.delegate = delegate
    this.dialogElement = null
    this.color = null
    this.itemName = itemName

    var colorPicker = this
    var createChoice = function(r,g,b) {
        var baseColor = sprintf("%d,%d,%d,1", r,g,b)
        var fillColor = sprintf("rgba(%d,%d,%d,0.4)", r, g, b)
        var borderColor = sprintf("5px solid rgba(%d,%d,%d,1.0)", r, g, b)
        var colorChoice = $(sprintf("<span class='color-choice' data-color='%s'></span>", baseColor))
        colorChoice.css("background-color", fillColor)
        colorChoice.css("border", borderColor)

        $(colorChoice).click(function() {
            color = $(this).attr("data-color").split(",")
            delegate.selectedColor(color)
        })

        return colorChoice
    }

    var colorChoices = $("<div class='color-choices'></div>")

    var colorRows = [ 
        [[255,0,0],[0,255,0],[0,102,255],[255,255,0],[0,255,255],[255,0,255], [255,255,255]],
        [[128,0,0],[0,128,0],[0,0,128],[128,128,0],[0,128,128],[128,0,128], [0,0,0]]
    ]

    for (var r = 0; r < colorRows.length; ++r) {
        var colorRow = $("<div class='color-choice-row'></div>")
        for (var i = 0; i < colorRows[r].length; ++i) {
            var color = colorRows[r][i]
            var colorChoice = createChoice(color[0], color[1], color[2])
            colorRow.append(colorChoice)
        }
        colorChoices.append(colorRow)
    }

    var title = this.itemName ? sprintf("Color for \"%s\"", this.itemName) : "Color"

    this.dialogElement = colorChoices
    this.dialogElement.dialog({
        autoOpen: false,
        buttons: [{
            text: "Close",
            click: function() {
                $(this).dialog("close")
            }
        }],
        dialogClass: "ui-dialog-color-picker",
        title: title
    })
}

ColorPicker.prototype.open = function() {
    this.dialogElement.dialog("open")
}

//CUSTOM LAYERS

var ClickPassingGeoJSON = L.GeoJSON.extend({
    options: {
        pointToLayer: function(feature, latlng) {
            return L.marker.svgMarker(latlng)
        }
    },
    initialize: function(geoJSON, options) {
        options = L.Util.setOptions(this, options)

        L.GeoJSON.prototype.initialize.call(this, geoJSON, options)

        mapViewDelegate = options.mapViewDelegate
        if (mapViewDelegate) {
            if (mapViewDelegate.mapViewClicked) {
                this.on("click", function(e) {
                    mapViewDelegate.mapViewClicked(e.latlng)
                })
            }
            this.on("dblclick", function(e) {
                var zoomLevel = mapViewDelegate.mapView.map.getZoom()
            })
        }
    }
})

//the use of the layer implies a crossing over the meridian
var AntimeridianAdjustedGeoJSON = ClickPassingGeoJSON.extend({
    initialize: function(geoJSON, options) {
        options = options || {}

        if (!options.coordsToLatLng) {
            options.coordsToLatLng = function(lnglat) {
                var lat = lnglat[1]
                var lng = lnglat[0]

                //convert to lat < -180 form e.g. 179 to -181
                if (lng > 0) { 
                    lng = -360 + lng 
                }

                return [lat,lng]
            }
        }

        ClickPassingGeoJSON.prototype.initialize.call(this, geoJSON, options)
    }
})

L.GeoJSON.include({
    addDataFromURL: function(url, loadStartFunction, loadEndFunction, progressFunction, timeoutFunction) {
        var layer = this

        if (loadStartFunction) { loadStartFunction() }

        var request = new XMLHttpRequest()
        request.open("GET", url, true)
        if (progressFunction) {
            request.onprogress = progressFunction
        }
        if (timeoutFunction) {
            request.ontimeout = timeoutFunction
        }
        request.onreadystatechange = function() {
            if (request.readyState == XHR_DONE && request.status == HTTP_OK) {
                try {
                    var data = JSON.parse(request.responseText)
                    layer.addData(data)
                }
                catch (exception){
                    alert("Unable to load this item.")
                }
            }
            else if (request.readyState == XHR_DONE && request.status != HTTP_OK) {
                alert("Unable to load this item.")
            }

            if (loadEndFunction) { loadEndFunction() }
        }
        request.send()
    }
})

L.Rectangle.include({
    setOpacity: function(opacity) {
        this.setStyle({
            fillOpacity: L.Rectangle.prototype.options.fillOpacity * opacity,
            opacity: L.Rectangle.prototype.options.opacity * opacity
        })
    }
})

var DeferredGeoJSON = L.GeoJSON.extend({
    options: {
        "markerTextProperty": null,
        "onLoadEnd": null,
        "onLoadStart": null,
        "opacity": 1,
        "progressFunction": null,
        "timeoutFunction": null,
        "url": null
    },
    initialize: function(url, options) {
        options = L.Util.setOptions(this, options)
        options.url = url
        options.onEachFeature =  function(feature, layer) {
            var properties = feature.properties
            if (properties) {
                var popupText = $("<div></div>")
                for (var k in properties) {
                    if (k == "bbox") { continue }
                    var v = properties[k]
                    v = sprintf("%s", v).replace(/,/g, "<br>")
                    popupText.append($(sprintf("<div>%s: %s</div>", k,v)))
                }
                layer.bindPopup(popupText[0], { maxHeight: 400 })
            }
        }
        var layer = this
        options.pointToLayer = function(feature, latlng) {
            var textProperty = layer.options.markerTextProperty
            var text = textProperty && feature.properties[textProperty] ? feature.properties[textProperty] : null
            return L.marker.svgMarker(latlng, { "circleText": text })
        }

        L.GeoJSON.prototype.initialize.call(this,null,options)

        this._loadStartFunction = null
        this._loadEndFunction = null
    },
    onAdd: function(map) {
        if (this.options.url) {
            var layer = this
            this.addDataFromURL(this.options.url, 
                function() {
                    if (layer.options.onLoadStart) { layer.options.onLoadStart() }
                }, 
                function() {
                    if (layer.options.onLoadEnd) { layer.options.onLoadEnd() }
                    L.GeoJSON.prototype.onAdd.call(layer, map) 
                },
                layer.options.progressFunction
            )
        }
        else {
            L.GeoJSON.prototype.onAdd.call(this, map)
        }
    },
    onLoadEnd: function(loadEndFunction) { this.options.onLoadEnd = loadEndFunction },
    onLoadStart: function(loadStartFunction) { this.options.onLoadStart = loadStartFunction },
    setOpacity: function(opacity) {
        this.options.opacity = opacity
        this.setStyle({
            fillOpacity: DeferredGeoJSON.prototype.options.fillOpacity * opacity,
            opacity: DeferredGeoJSON.prototype.options.opacity * opacity
        })
    }
})

L.DivIcon.SVGIcon = L.DivIcon.extend({
    options: {
        "circleText": "",
        "className": "svg-icon",
        "circleAnchor": null, //defaults to 
        "circleColor": null, //defaults to color
        "circleOpacity": null, // defaults to opacity
        "circleFillColor": "rgb(255,255,255)",
        "circleFillOpacity": null, //default to opacity 
        "circleRatio": 0.5,
        "circleWeight": null, //defaults to weight
        "color": "rgb(0,102,255)",
        "fillColor": null, // defaults to color
        "fillOpacity": 0.4,
        "fontColor": "rgb(0, 0, 0)",
        "fontOpacity": "1",
        "fontSize": null, // defaults to iconSize.x/4
        "iconAnchor": null, //defaults to [iconSize.x/2, iconSize.y] (point tip)
        "iconSize": L.point(32,48),
        "opacity": 1,
        "popupAnchor": null,
        "weight": 2
    },
    initialize: function(options) {
        options = L.Util.setOptions(this, options)

        //iconSize needs to be converted to a Point object if it is not passed as one
        options.iconSize = L.point(options.iconSize)

        //in addition to setting option dependant defaults, Point-based options are converted to Point objects
        if (!options.circleAnchor) {
            options.circleAnchor = L.point(Number(options.iconSize.x)/2, Number(options.iconSize.x)/2)
        }
        else {
            options.circleAnchor = L.point(options.circleAnchor)
        }
        if (!options.circleColor) {
            options.circleColor = options.color
        }
        if (!options.circleFillOpacity) {
            options.circleFillOpacity = options.opacity
        }
        if (!options.circleOpacity) {
            options.circleOpacity = options.opacity
        }
        if (!options.circleWeight) {
            options.circleWeight = options.weight
        }
        if (!options.fillColor) { 
            options.fillColor = options.color
        }
        if (!options.fontSize) {
            options.fontSize = Number(options.iconSize.x/4) 
        }
        if (!options.iconAnchor) {
            options.iconAnchor = L.point(Number(options.iconSize.x)/2, Number(options.iconSize.y))
        }
        else {
            options.iconAnchor = L.point(options.iconAnchor)
        }
        if (!options.popupAnchor) {
            options.popupAnchor = L.point(0, (-0.75)*(options.iconSize.y))
        }
        else {
            options.popupAnchor = L.point(options.iconAnchor)
        }

        var path = this._createPath()
        var circle = this._createCircle()

        options.html = this._createSVG()
    },
    _createCircle: function() {
        var cx = Number(this.options.circleAnchor.x) 
        var cy = Number(this.options.circleAnchor.y)
        var radius = this.options.iconSize.x/2 * Number(this.options.circleRatio)
        var fill = this.options.circleFillColor
        var fillOpacity = this.options.circleFillOpacity
        var stroke = this.options.circleColor
        var strokeOpacity = this.options.circleOpacity
        var strokeWidth = this.options.circleWeight
        var className = this.options.className + "-circle"

        var circle = '<circle class="' + className + '" cx="' + cx + '" cy="' + cy + '" r="' + radius + 
            '" fill="' + fill + '" fill-opacity="'+ fillOpacity + 
            '" stroke="' + stroke + '" stroke-opacity=' + strokeOpacity + '" stroke-width="' + strokeWidth + '"/>'

        return circle
    },
    _createPathDescription: function() {
        var height = Number(this.options.iconSize.y)
        var width = Number(this.options.iconSize.x)
        var weight = Number(this.options.weight)
        var margin = weight / 2

        var startPoint = "M " + margin + " " + (width/2) + " "
        var leftLine = "L " + (width/2) + " " + (height - weight) + " "
        var rightLine = "L " + (width - margin) + " " + (width/2) + " "
        var arc = "A " + (width/4) + " " + (width/4) + " 0 0 0 " + margin + " " + (width/2) + " Z"

        var d = startPoint + leftLine + rightLine + arc

        return d
    },
    _createPath: function() {
        var pathDescription = this._createPathDescription()
        var strokeWidth = this.options.weight
        var stroke = this.options.color
        var strokeOpacity = this.options.Opacity
        var fill = this.options.fillColor
        var fillOpacity = this.options.fillOpacity
        var className = this.options.className + "-path"

        var path = '<path class="' + className + '" d="' + pathDescription + 
            '" stroke-width="' + strokeWidth + '" stroke="' + stroke + '" stroke-opacity="' + strokeOpacity +
            '" fill="' + fill + '" fill-opacity="' + fillOpacity + '"/>'

        return path
    },
    _createSVG: function() {
        var path = this._createPath()
        var circle = this._createCircle()
        var text = this._createText()
        var className = this.options.className + "-svg"

        var style = "width:" + this.options.iconSize.x + "; height:" + this.options.iconSize.y + ";"

        var svg = '<svg xmlns="http://www.w3.org/2000/svg" version="1.1" class="' + className + '" style="' + style + '">' + path + circle + text + '</svg>'

        return svg
    },
    _createText: function() {
        var fontSize = this.options.fontSize + "px"
        var lineHeight = Number(this.options.fontSize)
        var textColor = this.options.fontColor.replace("rgb(", "rgba(").replace(")", "," + this.options.fontOpacity + ")")
        var circleText = this.options.circleText

        var x = Number(this.options.iconSize.x) / 2
        var y = x + (lineHeight * 0.35) //35% was found experimentally 

        var text = '<text text-anchor="middle" x="' + x + '" y="' + y + '" style="font-size: ' + fontSize + '" fill="' + textColor + '">' + circleText + '</text>'

        return text

    }
})

L.divIcon.svgIcon = function(options) {
    return new L.DivIcon.SVGIcon(options)
}

L.Marker.SVGMarker = L.Marker.extend({
    options: {
        "iconFactory": L.divIcon.svgIcon,
        "iconOptions": {}
    },
    initialize: function(latlng, options) {
        options = L.Util.setOptions(this, options)
        options.icon = options.iconFactory(options.iconOptions)
        this._latlng = latlng
    },
    onAdd: function(map) {
        L.Marker.prototype.onAdd.call(this, map)
    },
    setStyle: function(style) {
        if (this._icon) {
            var svg = this._icon.children[0]
            var iconBody = this._icon.children[0].children[0]
            var iconCircle = this._icon.children[0].children[1]

            if (style.color && !style.iconOptions) {
                var stroke = style.color.replace("rgb","rgba").replace(")", ","+this.options.icon.options.opacity+")")
                var fill = style.color.replace("rgb","rgba").replace(")", ","+this.options.icon.options.fillOpacity+")")
                iconBody.setAttribute("stroke", stroke)
                iconBody.setAttribute("fill", fill)
                iconCircle.setAttribute("stroke", stroke)

                this.options.icon.fillColor = fill
                this.options.icon.color = stroke
                this.options.icon.circleColor = stroke
            }
            if (style.opacity) {
                this.setOpacity(style.opacity)
            }
            if (style.iconOptions) {
                if (style.color) { style.iconOptions.color = style.color }
                iconOptions = L.Util.setOptions(this.options.icon, style.iconOptions)
                this.setIcon(this.options.iconFactory(iconOptions))
            }
        }
    }
})

L.marker.svgMarker = function(latlng, options) {
    return new L.Marker.SVGMarker(latlng, options)
}

L.DivIcon.SVGIcon.BookIcon = L.DivIcon.SVGIcon.extend({
    options: {
        "circleWeight": 1,
        "iconSize": L.point(48,48)
    },
    _createCircle: function() {
        return this._createInnerBook()
    },
    _createInnerBook: function() {
        var pathDescription = this._createInnerBookPathDescription()
        var strokeWidth = this.options.circleWeight
        var stroke = this.options.circleColor.replace("rgb(", "rgba(").replace(")", "," + this.options.circleOpacity + ")")
        var fill = this.options.circleFillColor.replace("rgb(", "rgba(").replace(")", "," + this.options.circleFillOpacity + ")")
        var className = this.options.className + "-path"

        var path = '<path class="' + className + '" d="' + pathDescription + '" stroke-width="' + strokeWidth + '" stroke="' + stroke + '" fill="' + fill + '"/>'

        return path
    },
    _createInnerBookPathDescription: function() {
        var tHeight = Number(this.options.iconSize.y) 
        var tWidth = Number(this.options.iconSize.x)
        var weight = Number(this.options.circleWeight)
        var margin = weight / 2

        var height = tHeight * (3/4)
        var width = tWidth * (3/4)

        var startPoint = sprintf("M %f %f", tWidth/8, height/12 + margin)
        var leftSide = sprintf("L %f %f", tWidth/8, height + tHeight/8 - margin)
        var bottomLeft = sprintf("A %f %f 0 0 1 %f %f", width, height/4, tWidth/2, tHeight - margin)
        var bottomRight = sprintf("A %f %f 0 0 1 %f %f", width, height/4, width + tWidth/8, height + tHeight/8 - margin)
        var rightSide = sprintf("L %f %f", width + tWidth / 8, height/12 + margin)
        var topRight = sprintf("A %f %f 0 0 0 %f %f", width/2, height/2, tWidth/2, height/6)
        var topLeft = sprintf("A %f %f 0 0 0 %f %f", width/2, height/2, tWidth/8, height/12 + margin)
        var end = "Z"

        var d = startPoint + leftSide + bottomLeft + bottomRight + rightSide + topRight + topLeft + end

        return d
    },
    _createPathDescription: function() {
        var height = Number(this.options.iconSize.y)
        var width = Number(this.options.iconSize.x)
        var weight = Number(this.options.weight)
        var margin = weight / 2

        var startPoint = sprintf("M %f %f ", margin, margin)
        var leftSide = sprintf("L %f %f ", margin, (5/6) * height)
        var bottomLeft = sprintf("L %f %f ", width/2, height - margin)
        var bottomRight = sprintf("L %f %f ", width - margin, (5/6) * height)
        var rightSide = sprintf("L %f %f ", width - margin, margin)
        var topRight = sprintf("L %f %f ", width / 2, height / 6)
        var topLeft = sprintf("L %f %f ", margin, margin)
        var end = "Z"

        var d = startPoint + leftSide + bottomLeft + bottomRight + rightSide + topRight + topLeft + end

        return d
    },
    _createText: function() {
        var fontSize = this.options.fontSize + "px"
        var lineHeight = Number(this.options.fontSize)
        var textColor = this.options.fontColor.replace("rgb(", "rgba(").replace(")", "," + this.options.fontOpacity + ")")
        var circleText = this.options.circleText
        var textParts = circleText.split("\n")
        var x = Number(this.options.iconSize.x) / 2

        var text = ""

        if (textParts.length == 1) {
            var y = x + (lineHeight * 0.35) //35% was found experimentally 
            text = '<text text-anchor="middle" x="' + x + '" y="' + y + '" style="font-size: ' + fontSize + '" fill="' + textColor + '">' + circleText + '</text>'
        }
        else {
            var y = x/4 + lineHeight
            text = '<text text-anchor="middle" x="' + x + '" y="' + y + '" style="font-size: ' + fontSize + '" fill="' + textColor + '">' + textParts[0] + '</text>'
            y = x/2 + 2 * lineHeight
            text += '<text text-anchor="middle" x="' + x + '" y="' + y + '" style="font-size: ' + fontSize + '" fill="' + textColor + '">' + textParts[1] + '</text>'
        }

        return text
    }
})

L.divIcon.svgIcon.bookIcon = function(options) {
    return new L.DivIcon.SVGIcon.BookIcon(options)
}

L.Marker.SVGMarker.BookMarker =  L.Marker.SVGMarker.extend({
    options: {
        "iconFactory": L.divIcon.svgIcon.bookIcon
    },
    bringToFront: function() {
    }
})

L.marker.svgMarker.bookMarker = function(options) {
    return new L.Marker.SVGMarker.BookMarker(options)
}

L.LayerGroup.include({
    bringToFront: function() {
        this.eachLayer(function(layer) {
            layer.bringToFront()
        })
    },
    setOpacity: function(opacity) {
        this.options.opacity = opacity
        this.eachLayer(function(layer) {
            layer.setOpacity(opacity)
        })
    },
    setStyle: function(style) {
        this.eachLayer(function(layer) {
            layer.setStyle(style)
        })
    }
})

//Bug(?) in Leaflet reset opacity on vector layers to 1 with regular dictionaries
function LeafletOptions(options) {
    for (var k in options) {
        this[k] = options[k]
    }
}
