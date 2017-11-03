// From https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Object/keys (CC-BY-SA 2.5)
if (!Object.keys) {
  Object.keys = (function() {
    'use strict';
    var hasOwnProperty = Object.prototype.hasOwnProperty,
        hasDontEnumBug = !({ toString: null }).propertyIsEnumerable('toString'),
        dontEnums = [
          'toString',
          'toLocaleString',
          'valueOf',
          'hasOwnProperty',
          'isPrototypeOf',
          'propertyIsEnumerable',
          'constructor'
        ],
        dontEnumsLength = dontEnums.length;

    return function(obj) {
      if (typeof obj !== 'object' && (typeof obj !== 'function' || obj === null)) {
        throw new TypeError('Object.keys called on non-object');
      }

      var result = [], prop, i;

      for (prop in obj) {
        if (hasOwnProperty.call(obj, prop)) {
          result.push(prop);
        }
      }

      if (hasDontEnumBug) {
        for (i = 0; i < dontEnumsLength; i++) {
          if (hasOwnProperty.call(obj, dontEnums[i])) {
            result.push(dontEnums[i]);
          }
        }
      }
      return result;
    };
  }());
}

//Replaces objects keys in place
Object.replace = function(dictionary, newKVs) {
    for (var k in dictionary) {
        delete dictionary[k]
    }

    for (var newK in newKVs) {
        dictionary[newK] = newKVs[newK]
    }
}

//returns a copy of the string with the first letter capitalized
String.prototype.capitalize = function() {
    var firstLetter = this[0].toUpperCase()
    var restOfString = this.substring(1)

    return firstLetter + restOfString
}

//https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/String/endsWith
if (!String.prototype.endsWith) {
  String.prototype.endsWith = function(searchString, position) {
      var subjectString = this.toString();
      if (typeof position !== 'number' || !isFinite(position) || Math.floor(position) !== position || position > subjectString.length) {
        position = subjectString.length;
      }
      position -= searchString.length;
      var lastIndex = subjectString.indexOf(searchString, position);
      return lastIndex !== -1 && lastIndex === position;
  };
}

//returns pixels per point
if (!window.devicePixelRatio) {
    if (window.screen.deviceXDPI && window.screen.logicalXDPI) {
        window.devicePixelRatio = window.screen.deviceXDPI / window.screen.logicalXDPI
    }
    else {
        window.devicePixelRatio = 1
    }
}
