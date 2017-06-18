GraphCtrl = angular.module('pubAssistantClient').controller('GraphCtrl', ['$scope', '$http', '$timeout', '$log',
 function($scope, $http, $timeout, $log) {
    $scope.keywordQueryText = '';
    $scope.keywordSearchResults = null;
    $scope.keywordSearchPromise = null;
    $scope.selectedKeywords = {};
    $scope.showSelectedKeywords = false;
    $scope.publicationQuery = '';
    $scope.publicationSearchResults = null;
    $scope.publicationSearchPromise = null;
    $scope.selectedPublications = {};
    $scope.showSelectedPublications = false;
    $scope.graphDataRequestPending = false;
    $scope.graphDataRequestError = false;
    $scope.keywordRequestPending = false;
    $scope.keywordRequestError = false;
    $scope.publicationRequestPending = false;
    $scope.publicationRequestError = false;

    $scope.graph_object = {};
    $scope.series = [];
    $scope.labels = [];
    $scope.data = [[]];

    $scope.keypressTimeout = 500;

    $scope.keywordQuery = function() {
        $scope.keywordRequestError = false;
        $scope.keywordRequestPending = true;
        $scope.keywordSearchResults = null;
        $http.get(urls.keywordSearchUrl, {params: {'query': $scope.keywordQueryText}}).then(
            function successCallback(response) {
                $scope.keywordRequestPending = false;
                $scope.keywordSearchResults = response.data;
            }, function failCallback(response) {
                $scope.keywordRequestPending = false;
                $scope.keywordRequestError = true;
            });
    };

    $scope.onKeywordQuery = function() {
        if ($scope.keywordSearchPromise) {
            $timeout.cancel($scope.keywordSearchPromise);
        }
        length = $scope.keywordQueryText.length;
        if (length > 0) {
            $scope.keywordSearchPromise = $timeout($scope.keywordQuery, $scope.keypressTimeout);
        } else {
            $scope.keywordSearchResults = null;
        }
    };

    $scope.addKeyword = function(keyword) {
        if (!$scope.selectedKeywords.hasOwnProperty(keyword.id)) {
            $scope.selectedKeywords[keyword.id] = keyword;
            $scope.fillDataForKeyword(keyword);
            $scope.showSelectedKeywords = true;
        }
    };

    $scope.removeKeyword = function(keyword) {
        if ($scope.selectedKeywords.hasOwnProperty(keyword.id)) {
            $scope.deleteSeriesData(keyword.keyword);
            delete $scope.selectedKeywords[keyword.id];
            if (Object.keys($scope.selectedKeywords).length == 0) {
                $scope.showSelectedKeywords = false;
            }
        }
    };

    $scope.clearKeywords = function() {
        $scope.graph_object = {};
        $scope.series = [];
        $scope.generateGraphData();
        $scope.selectedKeywords = {};
        $scope.showSelectedKeywords = false;
    };

    $scope.publicationQuery = function() {
        $scope.publicationRequestError = false;
        $scope.publicationRequestPending = true;
        $scope.publicationSearchResults = null;
        $http.get(urls.publicationSearchUrl, {params: {'query': $scope.publicationQueryText}}).then(
            function successCallback(response) {
                $scope.publicationRequestPending = false;
                $scope.publicationSearchResults = response.data;
            }, function failCallback(response) {
                $scope.publicationRequestPending = false;
                $scope.publicationRequestError = true;
            });
    };

    $scope.onPublicationQuery = function() {
        if ($scope.publicationSearchPromise) {
            $timeout.cancel($scope.publicationSearchPromise);
        }
        length = $scope.publicationQueryText.length;
        if (length > 0) {
            $scope.publicationSearchPromise = $timeout($scope.publicationQuery, $scope.keypressTimeout);
        } else {
            $scope.publicationSearchResults = null;
        }
    };

    $scope.addPublication = function(publication) {
        $scope.selectedPublications[publication.id] = publication;
        $scope.refillData();
        $scope.showSelectedPublications = true;
    };

    $scope.removePublication = function(publication) {
        delete $scope.selectedPublications[publication.id];
        $scope.refillData();
        if (Object.keys($scope.selectedPublications).length == 0) {
            $scope.showSelectedPublications = false;
        }
    };

    $scope.clearPublications = function() {
        $scope.selectedPublications = {};
        $scope.refillData();
        $scope.showSelectedPublications = false;
    };

    $scope.generateGraphData = function() {
//        sort and fill labels
        $scope.labels = Object.keys($scope.graph_object).sort();
//      fill data
        $scope.data = [];
        for (var j = 0; j < $scope.series.length; ++j) {
            $scope.data.push([]);
            for (var i = 0; i < $scope.labels.length; i++) {
                $scope.data[j].push($scope.graph_object[$scope.labels[i]][j]);
            }
        }
//        $log.debug('$scope.graphObject: ' + JSON.stringify($scope.graph_object))
//        $log.debug('$scope.data: ' + JSON.stringify($scope.data))
    };

    $scope.deleteSeriesData = function(name) {
        for(var i = 0; i < $scope.series.length; i++) {
            if ($scope.series[i] === name) {
                for (key in $scope.graph_object) {
                    $scope.graph_object[key].splice(i, 1)
                }
                $scope.series.splice(i, 1);
                break;
            }
            $scope.data.push($scope.graph_object[$scope.labels[i]].slice());
        }
        $scope.generateGraphData();
    };

    $scope.mergeSeriesData = function(series_name, new_data) {
//      fill graph_object
        for (var key in new_data) {
            if (key === null || key === 'null') continue;
            if (!new_data.hasOwnProperty(key)) continue;
            if (!$scope.graph_object.hasOwnProperty(key)) {
                $scope.graph_object[key] = [];
                for(var i = 0; i < $scope.series.length; i++) {
                    $scope.graph_object[key].push(0);
                }
            }
            $scope.graph_object[key].push(new_data[key]);
        }
        $scope.series.push(series_name);
        $scope.generateGraphData();
    };

    $scope.fillDataForKeyword = function(keyword) {
        params = {keyword: keyword.id};
        if (Object.keys($scope.selectedPublications).length > 0) {
            var publication_ids = [];
            for (var key in $scope.selectedPublications) {
                if (!$scope.selectedPublications.hasOwnProperty(key)) continue;
                publication_ids.push($scope.selectedPublications[key].id);
            }
            params['publications'] = publication_ids.join();
        }
//        $log.debug('"publications":' + params['publications']);
        $scope.publicationRequestError = false;
        $scope.graphDataRequestPending = true;
        $http.get(urls.graphDataUrl, {params: params}).then(
            function successCallback(response) {
                $scope.graphDataRequestPending = false;
                $scope.mergeSeriesData(keyword.keyword, response.data)
            }, function failCallback(response) {
                $scope.graphDataRequestPending = false;
                $scope.publicationRequestError = true;
            });
    };

    $scope.refillData = function() {
        $scope.series = [];
        $scope.graph_object = {};
        for (key in $scope.selectedKeywords) {
            $scope.fillDataForKeyword($scope.selectedKeywords[key])
        }
    }
}]);