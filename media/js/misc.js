groupItems = function(items, minimumSimilarity, splitRegexp) {
    minimumSimilarity = minimumSimilarity || 1
    splitRegexp = splitRegexp || new RegExp("[ ,_]+", "g")
    if (items.length == 0) {
        return {}
    }
    if (items.length == 1) {
        var itemName = items[0].LayerDisplayName
        var groups = {}
        groups[itemName] = items
        return groups
    }
    if (items.length == 2) {
        var parts = splitNamesIntoParts(items, splitRegexp)
        var similarity = partsSimilarity(parts[0], parts[1])
        var groups = {}
        
        if (similarity >= minimumSimilarity) {
            var key = keyForGroup(items, splitRegexp)
            groups[key] = items
            return groups
        }
        else {
            groups[items[0].LayerDisplayName] = [items[0]]
            groups[items[1].LayerDisplayName] = [items[1]]
        }

        return groups
    }
    else {
        var groups = {}
        var parts = splitNamesIntoParts(items, splitRegexp)
        var currentGroup = []
        var similarity = null
        var previousSimilarity = null

        for (var i = 0; i < items.length; ++i) {
            var item = items[i]

            if (previousSimilarity == null && currentGroup.length == 0) { //new group
                currentGroup.push(item)
                continue
            }

            similarity = partsSimilarity(parts[i], parts[i-1])

            if (currentGroup.length == 1 && similarity < minimumSimilarity || (similarity != previousSimilarity && currentGroup.length > 1))  { //should start new group
                previousSimilarity = null
                var key = keyForGroup(currentGroup, splitRegexp)
                groups[key] = currentGroup
                currentGroup = []
                --i
            }
            else { //add to current group
                currentGroup.push(item)
                previousSimilarity = similarity
            }
        }
        groups[keyForGroup(currentGroup, splitRegexp)] = currentGroup //get key for last group and add
        return groups
    }
}

keyForGroup = function(keyGroup, splitRegexp) {
    if (keyGroup.length == 0) {
        return null
    }
    if (keyGroup.length == 1) {
        return keyGroup[0].LayerDisplayName
    }
    else {
        var splitString = splitRegexp.source
        var parts = splitNamesIntoParts([keyGroup[0], keyGroup[1]], splitRegexp)
        var key = keyGroup[0].LayerDisplayName

        if (parts[0].length == parts[1].length) {
            for (var i = 0; i < parts[0].length; ++i) {
                if (parts[0][i] != parts[1][i]) {
                    key = key.replace(parts[0][i], "&middot;&middot;&middot;")
                }
            }
        }
        else {
            var similarity = partsSimilarity(parts[0], parts[1])
            var similarParts = parts[0].splice(0,similarity)
            var regexpString = ""
            for (var i = 0; i < (similarParts.length - 1); ++i) {
                regexpString = sprintf("%s%s%s", regexpString, similarParts[i], splitString)
            }
            regexpString = sprintf("%s%s", regexpString, similarParts[similarParts.length-1])
            
            key = keyGroup[0].LayerDisplayName.match(regexpString)
        }

        key = sprintf("%s (%d items)", key, keyGroup.length)

        return key
    }
}

splitNamesIntoParts = function(items, splitRegexp) {
    var parts = []
    for (var i = 0; i < items.length; ++i) {
        var item = items[i]
        parts.push(item.LayerDisplayName.replace(splitRegexp, " ").split(" "))
    }

    return parts
}

partsSimilarity = function(parts1, parts2) {
    var length = parts1.length > parts2.length ? parts2.length : parts1.length

    for (var i = 0; i < length; ++i) {
        if (parts1[i] != parts2[i]) {
            break
        }
    }

    return i
}

stringSimilarity = partsSimilarity
